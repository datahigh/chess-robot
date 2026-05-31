# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Move -> PieceAction decomposition (pure Python, no ROS).

This module is the *crux* of the orchestrator: it turns a single chess move
(resolved against the authoritative ``python-chess`` board) into the ordered
sequence of physical pick/place operations the arm must perform.

It is deliberately ROS-free so the orchestration logic is importable and
unit-testable without a ROS graph, MoveIt, or hardware.  The ROS node converts
the :class:`PieceActionData` dataclasses returned here into
``chess_arm_interfaces/PieceAction`` messages 1:1 (same field names, same
``action_type`` integer constants); the dry-run prints them directly.

Decomposition rules (computed on the board state *before* the move is pushed):

* normal quiet move (e2e4)      -> [PICK_PLACE from->to]
* capture (exd5)                -> [CLEAR_CAPTURE to->GYn, PICK_PLACE from->to]
* castling (e1g1 / e1c1)        -> [PICK_PLACE king_from->king_to,
                                    MOVE_ROOK rook_from->rook_to]
* en passant (e5d6)             -> [CLEAR_EN_PASSANT captured_pawn->GYn,
                                    PICK_PLACE from->to]
* promotion (e7e8q)             -> [REMOVE_PROMOTED_PAWN from->GYn,
                                    PLACE_PROMOTION queen_src->to (piece='Q')]
* promotion + capture (e7xd8q)  -> prepend [CLEAR_CAPTURE to->GYn]

The engine is the source of truth; the move handed in here must already be a
legal ``chess.Move`` for ``board``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Dict, List, Optional, Tuple

import chess
import yaml

# ---------------------------------------------------------------------------
# PieceAction action_type constants -- MUST mirror
# chess_arm_interfaces/msg/PieceAction.msg exactly.
# ---------------------------------------------------------------------------
PICK_PLACE = 0
CLEAR_CAPTURE = 1
MOVE_ROOK = 2
CLEAR_EN_PASSANT = 3
REMOVE_PROMOTED_PAWN = 4
PLACE_PROMOTION = 5

ACTION_NAMES = {
    PICK_PLACE: 'PICK_PLACE',
    CLEAR_CAPTURE: 'CLEAR_CAPTURE',
    MOVE_ROOK: 'MOVE_ROOK',
    CLEAR_EN_PASSANT: 'CLEAR_EN_PASSANT',
    REMOVE_PROMOTED_PAWN: 'REMOVE_PROMOTED_PAWN',
    PLACE_PROMOTION: 'PLACE_PROMOTION',
}


@dataclass
class Point:
    """Mirror of geometry_msgs/Point (x, y, z in metres)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> Tuple[float, float, float]:
        """Return (x, y, z)."""
        return (self.x, self.y, self.z)


@dataclass
class PieceActionData:
    """Plain-data twin of chess_arm_interfaces/msg/PieceAction.

    Field names match the .msg exactly so the ROS node can copy them across
    without translation.  ``from_square`` / ``to_square`` may be a board square
    (``'e2'``) or a graveyard slot (``'GY3'``); the xyz points carry the world
    coordinates already looked up from board_coordinates.yaml.
    """

    action_type: int = PICK_PLACE
    from_square: str = ''
    to_square: str = ''
    from_xyz: Point = field(default_factory=Point)
    to_xyz: Point = field(default_factory=Point)
    piece: str = ''

    @property
    def action_name(self) -> str:
        """Human-readable name of this action's type."""
        return ACTION_NAMES.get(self.action_type, f'UNKNOWN({self.action_type})')

    def describe(self) -> str:
        """One-line human-readable summary of this action."""
        f = self.from_xyz
        t = self.to_xyz
        piece = f' piece={self.piece}' if self.piece else ''
        return (
            f'{self.action_name:<20} '
            f'{self.from_square:>4} ({f.x:+.3f},{f.y:+.3f},{f.z:.3f}) -> '
            f'{self.to_square:>4} ({t.x:+.3f},{t.y:+.3f},{t.z:.3f}){piece}'
        )


class BoardCoordinates:
    """Loads board_coordinates.yaml and resolves square/graveyard -> world xyz.

    By default the YAML is found via the installed ``chess_arm_description``
    share directory (so it tracks the single source of truth).  A path can be
    injected for tests that run outside a sourced ROS install.
    """

    def __init__(self, yaml_path: Optional[str] = None):
        if yaml_path is None:
            yaml_path = self._default_yaml_path()
        with open(yaml_path, 'r') as fh:
            data = yaml.safe_load(fh)

        self.path = yaml_path
        self.surface_z = float(data.get('surface_z', 0.0))
        self.grasp_z = float(data.get('grasp_z', 0.030))
        self.lift_z = float(data.get('lift_z', 0.110))
        self._squares: Dict[str, Dict[str, float]] = data['squares']
        self._graveyard: Dict[str, Dict[str, float]] = data['graveyard']

    @staticmethod
    def _default_yaml_path() -> str:
        from ament_index_python.packages import get_package_share_directory

        share = get_package_share_directory('chess_arm_description')
        return os.path.join(share, 'config', 'board_coordinates.yaml')

    # -- name -> xyz lookups (kept behind helpers per spec) ------------------

    def graveyard_slots(self) -> List[str]:
        """Return graveyard slot names sorted numerically (GY1..GY16)."""
        return sorted(self._graveyard.keys(), key=lambda s: int(s[2:]))

    def _xy(self, name: str) -> Tuple[float, float]:
        if name in self._squares:
            cell = self._squares[name]
        elif name in self._graveyard:
            cell = self._graveyard[name]
        else:
            raise KeyError(f'Unknown board location: {name!r}')
        return float(cell['x']), float(cell['y'])

    def grasp_point(self, name: str) -> Point:
        """Return world xyz to grasp the piece at ``name`` (grasp height)."""
        x, y = self._xy(name)
        return Point(x, y, self.grasp_z)

    def place_point(self, name: str) -> Point:
        """Return world xyz to place a piece at ``name`` (grasp height)."""
        x, y = self._xy(name)
        return Point(x, y, self.grasp_z)


class GraveyardAllocator:
    """Hands out free graveyard slots GY1..GYn for cleared pieces.

    The highest-numbered slot is reserved as the *source* of the spare
    promotion queen, so a cleared piece is never dropped onto it.  Cleared
    pieces fill from GY1 upward; promotions draw the spare queen from the
    reserved slot.
    """

    def __init__(self, coords: BoardCoordinates):
        self._coords = coords
        slots = coords.graveyard_slots()
        if not slots:
            raise ValueError('board_coordinates.yaml defines no graveyard slots')
        # Reserve the last slot as the spare-queen source.
        self.promotion_source_slot = slots[-1]
        self._free = list(slots[:-1])

    def reset(self) -> None:
        """Restore all clear slots and re-reserve the promotion source."""
        slots = self._coords.graveyard_slots()
        self.promotion_source_slot = slots[-1]
        self._free = list(slots[:-1])

    def next_slot(self) -> str:
        """Allocate the next free graveyard slot for a cleared piece."""
        if not self._free:
            raise RuntimeError('graveyard is full: no free slot for cleared piece')
        return self._free.pop(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _piece_symbol(board: chess.Board, square: int) -> str:
    piece = board.piece_at(square)
    return piece.symbol() if piece is not None else ''


def _rook_squares_for_castle(king_to: int) -> Tuple[int, int]:
    """Given the king's destination square, return (rook_from, rook_to).

    Standard chess castling: king moves two files toward the rook.

    * King to file g (h-side / kingside): rook h-file -> f-file.
    * King to file c (a-side / queenside): rook a-file -> d-file.

    Rook stays on the king's rank.
    """
    rank = chess.square_rank(king_to)
    to_file = chess.square_file(king_to)
    if to_file == chess.FILE_NAMES.index('g'):  # kingside
        rook_from = chess.square(chess.FILE_NAMES.index('h'), rank)
        rook_to = chess.square(chess.FILE_NAMES.index('f'), rank)
    elif to_file == chess.FILE_NAMES.index('c'):  # queenside
        rook_from = chess.square(chess.FILE_NAMES.index('a'), rank)
        rook_to = chess.square(chess.FILE_NAMES.index('d'), rank)
    else:
        raise ValueError(
            f'king destination {chess.square_name(king_to)} is not a castle target')
    return rook_from, rook_to


def _en_passant_captured_square(move: chess.Move) -> int:
    """Return the square of the pawn captured en passant.

    The captured pawn sits on the destination file but on the *origin* rank of
    the capturing pawn (one rank behind the destination, same file as the
    destination).
    """
    to_file = chess.square_file(move.to_square)
    from_rank = chess.square_rank(move.from_square)
    return chess.square(to_file, from_rank)


# ---------------------------------------------------------------------------
# The crux: move -> ordered PieceActionData list
# ---------------------------------------------------------------------------

def decompose_move(
    board: chess.Board,
    move: chess.Move,
    coords: BoardCoordinates,
    allocator: GraveyardAllocator,
) -> List[PieceActionData]:
    """Decompose ``move`` into the ordered physical actions for the arm.

    MUST be called on ``board`` *before* the move is pushed (it inspects the
    current occupancy to know what is being captured, etc.).  The caller is
    responsible for ``board.push(move)`` afterwards.

    :param board: authoritative board, with ``move`` legal and not yet pushed.
    :param move: the chess move to perform physically.
    :param coords: square/graveyard -> world xyz resolver.
    :param allocator: graveyard slot allocator (mutated as slots are consumed).
    :returns: ordered list of :class:`PieceActionData`; the arm executes them
        in order.  Clears always precede the placement they make room for.
    """
    if move not in board.legal_moves:
        raise ValueError(f'{move.uci()} is not legal in position {board.fen()}')

    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)
    mover_symbol = _piece_symbol(board, move.from_square)

    actions: List[PieceActionData] = []

    is_castle = board.is_castling(move)
    is_ep = board.is_en_passant(move)
    is_capture = board.is_capture(move)
    is_promotion = move.promotion is not None

    # --- 1. Castling: king first, then rook -------------------------------
    if is_castle:
        actions.append(
            PieceActionData(
                action_type=PICK_PLACE,
                from_square=from_sq,
                to_square=to_sq,
                from_xyz=coords.grasp_point(from_sq),
                to_xyz=coords.place_point(to_sq),
                piece=mover_symbol,
            ))
        rook_from, rook_to = _rook_squares_for_castle(move.to_square)
        rook_from_sq = chess.square_name(rook_from)
        rook_to_sq = chess.square_name(rook_to)
        actions.append(
            PieceActionData(
                action_type=MOVE_ROOK,
                from_square=rook_from_sq,
                to_square=rook_to_sq,
                from_xyz=coords.grasp_point(rook_from_sq),
                to_xyz=coords.place_point(rook_to_sq),
                piece=_piece_symbol(board, rook_from),
            ))
        return actions

    # --- 2. En passant: clear the captured pawn, then move the pawn -------
    if is_ep:
        cap_sq_idx = _en_passant_captured_square(move)
        cap_sq = chess.square_name(cap_sq_idx)
        slot = allocator.next_slot()
        actions.append(
            PieceActionData(
                action_type=CLEAR_EN_PASSANT,
                from_square=cap_sq,
                to_square=slot,
                from_xyz=coords.grasp_point(cap_sq),
                to_xyz=coords.place_point(slot),
                piece=_piece_symbol(board, cap_sq_idx),
            ))
        actions.append(
            PieceActionData(
                action_type=PICK_PLACE,
                from_square=from_sq,
                to_square=to_sq,
                from_xyz=coords.grasp_point(from_sq),
                to_xyz=coords.place_point(to_sq),
                piece=mover_symbol,
            ))
        return actions

    # --- 3. Ordinary capture (or capture-promotion): clear destination ----
    # For both plain captures and capture-promotions, the captured piece sits
    # on the destination square and must be cleared before anything lands.
    if is_capture:
        captured_symbol = _piece_symbol(board, move.to_square)
        slot = allocator.next_slot()
        actions.append(
            PieceActionData(
                action_type=CLEAR_CAPTURE,
                from_square=to_sq,
                to_square=slot,
                from_xyz=coords.grasp_point(to_sq),
                to_xyz=coords.place_point(slot),
                piece=captured_symbol,
            ))

    # --- 4. Promotion: remove pawn, place fetched promoted piece ----------
    if is_promotion:
        promo_letter = chess.piece_symbol(move.promotion).upper()  # 'q' -> 'Q'
        # Remove the promoting pawn off the board to a graveyard slot.
        pawn_slot = allocator.next_slot()
        actions.append(
            PieceActionData(
                action_type=REMOVE_PROMOTED_PAWN,
                from_square=from_sq,
                to_square=pawn_slot,
                from_xyz=coords.grasp_point(from_sq),
                to_xyz=coords.place_point(pawn_slot),
                piece=mover_symbol,
            ))
        # Fetch the spare promoted piece (default queen) and place on dest.
        queen_src = allocator.promotion_source_slot
        actions.append(
            PieceActionData(
                action_type=PLACE_PROMOTION,
                from_square=queen_src,
                to_square=to_sq,
                from_xyz=coords.grasp_point(queen_src),
                to_xyz=coords.place_point(to_sq),
                piece=promo_letter,
            ))
        return actions

    # --- 5. Quiet move or simple capture move (attacker relocation) -------
    actions.append(
        PieceActionData(
            action_type=PICK_PLACE,
            from_square=from_sq,
            to_square=to_sq,
            from_xyz=coords.grasp_point(from_sq),
            to_xyz=coords.place_point(to_sq),
            piece=mover_symbol,
        ))
    return actions
