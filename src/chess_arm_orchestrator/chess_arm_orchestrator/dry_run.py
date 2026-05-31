# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Standalone dry-run that plays a full game with NO ROS / NO MoveIt.

This proves the orchestration *logic* end-to-end::

    human move (scripted)
        -> ChessBrain resolves & pushes it onto the authoritative board
        -> ChessBrain asks Stockfish for the engine reply
        -> decompose_move() turns each move into PieceActions
        -> the action sequence is printed (what the arm would do)

It drives :class:`chess_arm_brain.brain.ChessBrain` directly when that package
is importable; otherwise it falls back to a small built-in brain that uses
``python-chess`` + Stockfish the same way (so the logic is still exercised even
before the brain package is on the path).

Run it with::

    python3 -m chess_arm_orchestrator.dry_run
    python3 -m chess_arm_orchestrator.dry_run --elo 1500
    python3 -m chess_arm_orchestrator.dry_run --no-engine   # logic only

Stockfish is opened LAZILY and guarded: if the binary is missing you get a
clear message and (with ``--no-engine`` or on engine failure) the scripted
special-case lines are still decomposed and printed.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

import chess

from chess_arm_orchestrator.piece_actions import (
    BoardCoordinates,
    decompose_move,
    GraveyardAllocator,
)

# A scripted human game that exercises the special cases the spec calls out:
# capture and castling.  White and Black are both scripted so this runs
# deterministically without Stockfish.
SCRIPT_MAIN: List[str] = [
    'e2e4', 'e7e5',
    'g1f3', 'b8c6',
    'f1c4', 'g8f6',
    'f3g5', 'd7d5',
    'e4d5', 'f6d5',   # exd5 (white capture), then Nxd5 (black capture)
    'e1g1',           # white castles kingside (O-O)
]

# En passant: reach a position where white plays exd6 e.p.
SCRIPT_EP: List[str] = [
    'e2e4', 'a7a6',
    'e4e5', 'd7d5',   # black pushes two -> white can take e.p.
    'e5d6',           # exd6 en passant
]

# Quiet promotion: march the c-pawn to b7 (capturing the b-pawn), with black's
# b8 knight already vacated to a6, then push b7-b8=Q onto an empty square.
SCRIPT_PROMO: List[str] = [
    'c2c4', 'b8a6',   # black knight leaves b8 so b8 will be empty
    'c4c5', 'g8f6',
    'c5c6', 'f6g8',
    'c6b7', 'g8f6',   # cxb7 (captures the b7 pawn); b8 now empty
    'b7b8q',          # b7-b8=Q -> quiet promotion onto the empty b8
]

# Capture-promotion: white pawn reaches b7 then bxa8=Q, capturing the a8 rook
# while promoting (exercises CLEAR_CAPTURE + REMOVE_PROMOTED_PAWN + PLACE).
SCRIPT_CAPTURE_PROMO: List[str] = [
    'c2c4', 'g8f6',
    'c4c5', 'f6g8',
    'c5c6', 'g8f6',
    'c6b7', 'f6g8',   # cxb7 (captures the b7 pawn)
    'b7a8q',          # bxa8=Q -> capture-promotion taking the a8 rook
]


class _FallbackBrain:
    """Minimal stand-in for chess_arm_brain.brain.ChessBrain.

    Implements just enough of the contract the dry-run relies on so the logic
    runs even before the real brain package is importable.  The real ChessBrain
    is preferred (see make_brain).
    """

    def __init__(self, elo=None, skill=None, movetime_ms=100):
        self.board = chess.Board()
        self._elo = elo
        self._skill = skill
        self._movetime_ms = movetime_ms
        self._engine = None  # opened lazily
        self._engine_failed = False

    # -- game state -------------------------------------------------------

    def push_human_uci(self, uci: str) -> chess.Move:
        """Validate and push a human move given in UCI form."""
        move = chess.Move.from_uci(uci)
        if move not in self.board.legal_moves:
            raise ValueError(f'illegal human move {uci} in {self.board.fen()}')
        self.board.push(move)
        return move

    def is_game_over(self) -> bool:
        """Return True if the game has ended."""
        return self.board.is_game_over()

    # -- engine (lazy) ----------------------------------------------------

    def _ensure_engine(self):
        if self._engine is not None or self._engine_failed:
            return self._engine
        try:
            import chess.engine

            self._engine = chess.engine.SimpleEngine.popen_uci('stockfish')
            opts = {}
            if self._elo is not None:
                opts['UCI_LimitStrength'] = True
                opts['UCI_Elo'] = int(self._elo)
            if self._skill is not None:
                opts['Skill Level'] = int(self._skill)
            if opts:
                try:
                    self._engine.configure(opts)
                except Exception as exc:  # noqa: BLE001
                    print(f'  (engine configure ignored: {exc})')
        except Exception as exc:  # noqa: BLE001 - binary missing etc.
            self._engine_failed = True
            print(
                '  [no Stockfish] engine reply unavailable '
                f'({type(exc).__name__}: {exc}). '
                "Install 'stockfish' or pass --no-engine.")
        return self._engine

    def engine_move(self) -> Optional[chess.Move]:
        """Return the engine's reply move, or None if no engine."""
        import chess.engine

        engine = self._ensure_engine()
        if engine is None:
            return None
        result = engine.play(
            self.board, chess.engine.Limit(time=self._movetime_ms / 1000.0))
        return result.move

    def close(self) -> None:
        """Shut down the engine subprocess if one was started."""
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:  # noqa: BLE001
                pass
            self._engine = None


def make_brain(elo, skill, movetime_ms, prefer_real=True):
    """Return a ChessBrain instance; prefer the real package, else fallback."""
    if prefer_real:
        try:
            from chess_arm_brain.brain import ChessBrain  # type: ignore

            # The real brain owns engine config + board; construct best-effort.
            try:
                return ChessBrain(elo=elo, skill=skill, movetime_ms=movetime_ms)
            except TypeError:
                # Tolerate a different constructor signature.
                return ChessBrain()
        except Exception:  # noqa: BLE001 - package not built yet / import error
            pass
    return _FallbackBrain(elo=elo, skill=skill, movetime_ms=movetime_ms)


def _board_of(brain) -> chess.Board:
    board = getattr(brain, 'board', None)
    if not isinstance(board, chess.Board):
        raise RuntimeError('brain does not expose a python-chess .board')
    return board


def _engine_reply(brain, use_engine: bool) -> Optional[chess.Move]:
    if not use_engine:
        return None
    if hasattr(brain, 'engine_move'):
        return brain.engine_move()
    return None


def _apply_and_print(brain, move, who, coords, allocator) -> bool:
    """Decompose ``move`` (on pre-push board), print actions, then push it.

    Returns False if the move is not legal (so the caller can stop cleanly).
    """
    board = _board_of(brain)
    if move not in board.legal_moves:
        print(f'  !! {who} move {move.uci()} illegal in {board.fen()} -- stopping')
        return False
    san = board.san(move)
    actions = decompose_move(board, move, coords, allocator)
    print(f'  {who}: {move.uci()} ({san})  ->  {len(actions)} action(s)')
    for i, action in enumerate(actions, start=1):
        print(f'      [{i}/{len(actions)}] {action.describe()}')
    board.push(move)
    return True


def play_scripted(script, coords, title, *, elo=None, skill=None,
                  movetime_ms=100, use_engine=False) -> None:
    """Play a fully scripted line, decomposing every ply.

    Both colours come from ``script`` so this runs deterministically with no
    engine.  (The engine path is exercised separately by play_vs_engine.)
    """
    print(f'\n=== {title} ===')
    brain = make_brain(elo, skill, movetime_ms, prefer_real=True)
    allocator = GraveyardAllocator(coords)
    try:
        board = _board_of(brain)
        move_no = 0
        for uci in script:
            who = 'White' if board.turn == chess.WHITE else 'Black'
            if board.turn == chess.WHITE:
                move_no += 1
                print(f'  -- move {move_no} --')
            move = chess.Move.from_uci(uci)
            if not _apply_and_print(brain, move, who, coords, allocator):
                break
            if board.is_game_over():
                print(f'  game over: {board.result()} ({board.outcome()})')
                break
    finally:
        if hasattr(brain, 'close'):
            brain.close()


def play_vs_engine(human_moves, coords, *, elo=None, skill=None,
                   movetime_ms=100, use_engine=True) -> None:
    """Play human (scripted white) vs engine (black): the real loop shape.

    For each human move: decompose+push it, then ask the engine for a reply and
    decompose+push that.  This mirrors the ROS state machine
    (DETECT->RESOLVE->ENGINE->PLAN->EXECUTE) without ROS.
    """
    print('\n=== Human (scripted) vs Stockfish (engine reply) ===')
    brain = make_brain(elo, skill, movetime_ms, prefer_real=True)
    allocator = GraveyardAllocator(coords)
    try:
        board = _board_of(brain)
        move_no = 0
        for uci in human_moves:
            move_no += 1
            print(f'  -- move {move_no} --')
            human = chess.Move.from_uci(uci)
            if not _apply_and_print(brain, human, 'Human', coords, allocator):
                break
            if board.is_game_over():
                print(f'  game over: {board.result()}')
                break
            reply = _engine_reply(brain, use_engine)
            if reply is None:
                # No engine -> the turn never flips back to the human, so the
                # remaining scripted human moves would be illegal. Stop cleanly
                # rather than spamming 'illegal move' warnings.
                print('  Engine: (no reply -- engine disabled/unavailable); '
                      'stopping the engine pass')
                break
            if not _apply_and_print(brain, reply, 'Engine', coords, allocator):
                break
            if board.is_game_over():
                print(f'  game over: {board.result()}')
                break
    finally:
        if hasattr(brain, 'close'):
            brain.close()


def _resolve_coords(yaml_path) -> BoardCoordinates:
    if yaml_path:
        return BoardCoordinates(yaml_path)
    try:
        return BoardCoordinates()  # via ament_index
    except Exception as exc:  # noqa: BLE001
        print(
            'Could not locate board_coordinates.yaml via ament '
            f'({type(exc).__name__}: {exc}).\n'
            'Source the workspace install, or pass --coords <path>.',
            file=sys.stderr)
        raise SystemExit(2)


def main(argv=None) -> int:
    """Run the scripted dry-run (and an optional engine pass)."""
    parser = argparse.ArgumentParser(
        description='Dry-run the chess-arm orchestration logic (no ROS).')
    parser.add_argument('--coords', default=None,
                        help='path to board_coordinates.yaml '
                             '(default: via chess_arm_description share dir)')
    parser.add_argument('--elo', type=int, default=None,
                        help='Stockfish UCI_Elo (enables UCI_LimitStrength)')
    parser.add_argument('--skill', type=int, default=None,
                        help='Stockfish Skill Level 0..20')
    parser.add_argument('--movetime', type=int, default=100,
                        help='engine movetime in ms (default 100)')
    parser.add_argument('--no-engine', action='store_true',
                        help='skip Stockfish; only the scripted special-case '
                             'lines run (logic-only, always works)')
    args = parser.parse_args(argv)

    coords = _resolve_coords(args.coords)
    print(f'board_coordinates: {coords.path}')
    print(f'grasp_z={coords.grasp_z}  lift_z={coords.lift_z}  '
          f'surface_z={coords.surface_z}')
    print(f'graveyard slots: {len(coords.graveyard_slots())} '
          '(promotion-queen source reserved)')

    # 1) Deterministic special-case lines -- always run, no engine needed.
    play_scripted(SCRIPT_MAIN, coords,
                  'Main line (capture + castling)', use_engine=False)
    play_scripted(SCRIPT_EP, coords,
                  'En passant line', use_engine=False)
    play_scripted(SCRIPT_PROMO, coords,
                  'Quiet promotion line (b8=Q)', use_engine=False)
    play_scripted(SCRIPT_CAPTURE_PROMO, coords,
                  'Capture-promotion line (bxa8=Q)', use_engine=False)

    # 2) Optional human-vs-engine pass exercising the full orchestration shape.
    if not args.no_engine:
        play_vs_engine(
            ['e2e4', 'd2d4', 'b1c3', 'f1c4', 'g1f3', 'e1g1'],
            coords, elo=args.elo, skill=args.skill,
            movetime_ms=args.movetime, use_engine=True)
    else:
        print('\n(--no-engine) skipping the Stockfish human-vs-engine pass.')

    print('\nDry-run complete: orchestration logic exercised end-to-end.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
