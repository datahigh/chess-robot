# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Scripted-game RUNNER that drives the arm through MoveIt in simulation.

This is a *standalone* rclpy node -- it does NOT use the orchestrator state
machine (no DETECT/RESOLVE/VERIFY service round-trips, no vision).  Its sole job
is to prove the **physical pick/place loop** end-to-end against a live
``move_group`` (mock_components sim): for a short scripted sequence of chess
moves it decomposes each move with :class:`chess_arm_brain.brain.ChessBrain`,
enriches the resulting piece actions with world coordinates, and feeds the
ordered action list to a :class:`chess_arm_orchestrator.executors.MoveItExecutor`
bound to this node.

It deliberately exercises **every special case on the arm side** by resetting
the authoritative board to a verified FEN per scenario (a single continuous
legal line that contains a normal move, a capture, a kingside castle, an en
passant, and a promotion is awkward to construct and slow to play; independent
verified FENs keep the sim bounded and the intent obvious):

    1. normal move        e2e4   (PICK_PLACE)
    2. capture            e4d5   (CLEAR_CAPTURE -> PICK_PLACE)
    3. kingside castle    e1g1   (PICK_PLACE king + MOVE_ROOK)
    4. en passant         e5f6   (CLEAR_EN_PASSANT -> PICK_PLACE)
    5. promotion          a7a8q  (REMOVE_PROMOTED_PAWN -> PLACE_PROMOTION)
    6. capture-promotion  b7a8q  (CLEAR_CAPTURE -> REMOVE_PROMOTED_PAWN ->
                                  PLACE_PROMOTION)  [bonus]

Each scenario is independent, so we ``brain.reset(fen)`` before decomposing and
``brain.push(move)`` after a successful execute (advancing the authoritative
board exactly as the real game loop would).

Run it (with a live move_group up -- see game_moveit.launch.py)::

    ros2 launch chess_arm_orchestrator game_moveit.launch.py
    ros2 run chess_arm_orchestrator play_sim_game

Pick a subset of scenarios via a ROS parameter or argv (1-based indices or
names)::

    ros2 run chess_arm_orchestrator play_sim_game --ros-args -p scenarios:='[1,3]'
    ros2 run chess_arm_orchestrator play_sim_game normal castle
    ros2 run chess_arm_orchestrator play_sim_game 1 2

By default a small bounded subset runs (normal + castle) to keep sim time short;
pass ``all`` to run every scenario including the special cases.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Sequence, Tuple

import chess
from chess_arm_brain.brain import BoardCoordinates, ChessBrain
from chess_arm_orchestrator.executors import describe_action, MoveItExecutor
from chess_arm_orchestrator.piece_actions import Point as _Point
from chess_arm_orchestrator.piece_actions import PieceActionData
import rclpy
from rclpy.node import Node


# ---------------------------------------------------------------------------
# Scenario table: (name, FEN, uci).  Every FEN+move is verified legal against
# python-chess; each move type is what we want the arm to physically perform.
# ---------------------------------------------------------------------------
class Scenario:
    """One scripted arm-side test: a board position + the move to perform."""

    def __init__(self, name: str, fen: str, uci: str, note: str = ''):
        self.name = name
        self.fen = fen
        self.uci = uci
        self.note = note


SCENARIOS: List[Scenario] = [
    Scenario(
        'normal',
        chess.STARTING_FEN,
        'e2e4',
        'quiet move from the opening position -> PICK_PLACE',
    ),
    Scenario(
        'capture',
        'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2',
        'e4d5',
        'pawn takes pawn -> CLEAR_CAPTURE then PICK_PLACE',
    ),
    Scenario(
        'castle',
        'rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4',
        'e1g1',
        'white O-O -> PICK_PLACE (king) then MOVE_ROOK',
    ),
    Scenario(
        'en_passant',
        'rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3',
        'e5f6',
        'exf6 e.p. -> CLEAR_EN_PASSANT then PICK_PLACE',
    ),
    Scenario(
        'promotion',
        '8/P6k/8/8/8/8/6K1/8 w - - 0 1',
        'a7a8q',
        'a8=Q on empty square -> REMOVE_PROMOTED_PAWN then PLACE_PROMOTION',
    ),
    Scenario(
        'capture_promotion',
        'rn5k/1P6/8/8/8/8/6K1/8 w - - 0 1',
        'b7a8q',
        'bxa8=Q -> CLEAR_CAPTURE, REMOVE_PROMOTED_PAWN, PLACE_PROMOTION',
    ),
]

# Default subset: keep sim time bounded.  Override with the `scenarios` param or
# argv.  'normal' + 'castle' touch PICK_PLACE, MOVE_ROOK and a multi-action move.
DEFAULT_SUBSET = ['normal', 'castle']

_NAME_BY_INDEX = {i + 1: s.name for i, s in enumerate(SCENARIOS)}
_SCENARIO_BY_NAME = {s.name: s for s in SCENARIOS}


# ---------------------------------------------------------------------------
# brain dict -> PieceActionData (the canonical executor contract).
# ---------------------------------------------------------------------------
def _to_point(xyz) -> _Point:
    """Coerce a 3-tuple/list (brain xyz) or a Point-like into a Point."""
    if xyz is None:
        return _Point()
    # Already Point-like (has .x/.y/.z)?
    if hasattr(xyz, 'x') and hasattr(xyz, 'y') and hasattr(xyz, 'z'):
        return _Point(float(xyz.x), float(xyz.y), float(xyz.z))
    x, y, z = xyz
    return _Point(float(x), float(y), float(z))


def _enriched_dict_to_action(d: dict) -> PieceActionData:
    """Convert a ``ChessBrain.with_coordinates`` dict into a PieceActionData.

    The brain returns plain dicts with ``from_xyz`` / ``to_xyz`` as ``(x,y,z)``
    tuples; the executors consume objects with attribute access and Point xyz
    (the ``chess_arm_interfaces/PieceAction`` shape).  This bridges the two.
    """
    return PieceActionData(
        action_type=int(d['action_type']),
        from_square=str(d['from_square']),
        to_square=str(d['to_square']),
        from_xyz=_to_point(d.get('from_xyz')),
        to_xyz=_to_point(d.get('to_xyz')),
        piece=str(d.get('piece', '') or ''),
    )


# ---------------------------------------------------------------------------
# Executor construction -- robust to the final MoveItExecutor signature.
# ---------------------------------------------------------------------------
def _build_moveit_executor(node: Node) -> MoveItExecutor:
    """Instantiate MoveItExecutor bound to ``node`` (executors.py owns its API).

    The real MoveItExecutor needs the rclpy node to create its action clients
    for ``/move_action`` (MoveGroup) and ``/gripper_controller/gripper_cmd``,
    and to spin while it blocks on each goal.  Its signature is
    ``MoveItExecutor(logger=None, node=None)`` with ``node`` required.
    """
    return MoveItExecutor(logger=node.get_logger(), node=node)


# ---------------------------------------------------------------------------
# The runner node.
# ---------------------------------------------------------------------------
class PlaySimGame(Node):
    """Standalone node: play a scripted arm-side pick/place sequence in sim."""

    def __init__(self):
        super().__init__('play_sim_game')

        # `scenarios` param: list of ints (1-based) or names, or ['all'].
        self.declare_parameter('scenarios', [''])

        # Authoritative board + coordinates (board centre is the world origin).
        try:
            coords = BoardCoordinates.from_package_share()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(
                'could not load board_coordinates.yaml from '
                f'chess_arm_description share: {exc}')
            raise
        self.brain = ChessBrain(coordinates=coords)
        self.get_logger().info(
            f'board coords loaded (grasp_z={coords.grasp_z}, '
            f'lift_z={coords.lift_z}, surface_z={coords.surface_z})')

        # The MoveIt-backed executor (drives move_group + gripper for this node).
        self.executor_ = _build_moveit_executor(self)
        self.get_logger().info(
            f'executor = {type(self.executor_).__name__} (MoveIt / sim)')

    # -- scenario selection -------------------------------------------------

    def _selected_scenarios(self, argv: Optional[Sequence[str]]) -> List[Scenario]:
        """Resolve the scenario subset from argv, then the ROS param, then the
        bounded default.  Accepts 1-based indices, names, or 'all'."""
        tokens: List[str] = []

        # argv takes precedence (positional, after ros2 run strips --ros-args).
        if argv:
            tokens = [t for t in argv if t and not t.startswith('-')]

        if not tokens:
            param = self.get_parameter('scenarios').value
            if isinstance(param, (list, tuple)):
                tokens = [str(t) for t in param if str(t).strip()]
            elif param is not None and str(param).strip():
                tokens = [str(param)]

        if not tokens:
            tokens = list(DEFAULT_SUBSET)

        if any(t.lower() == 'all' for t in tokens):
            return list(SCENARIOS)

        chosen: List[Scenario] = []
        for t in tokens:
            t = t.strip()
            if t.isdigit():
                name = _NAME_BY_INDEX.get(int(t))
                if name is None:
                    self.get_logger().warning(f'no scenario #{t}; skipping')
                    continue
                chosen.append(_SCENARIO_BY_NAME[name])
            elif t in _SCENARIO_BY_NAME:
                chosen.append(_SCENARIO_BY_NAME[t])
            else:
                self.get_logger().warning(f'unknown scenario {t!r}; skipping')
        return chosen or list(SCENARIOS[:1])

    # -- the run ------------------------------------------------------------

    def _run_scenario(self, sc: Scenario) -> Tuple[bool, str]:
        """Decompose -> enrich -> execute -> push one scripted move."""
        self.get_logger().info('')
        self.get_logger().info(f'=== scenario: {sc.name} ===')
        if sc.note:
            self.get_logger().info(f'    {sc.note}')

        # Reset the authoritative board to this scenario's position.  reset()
        # also re-arms the graveyard allocator so slot numbering is fresh.
        self.brain.reset(sc.fen)
        board = self.brain.board

        move = chess.Move.from_uci(sc.uci)
        if move not in board.legal_moves:
            return False, f'{sc.uci} illegal in {board.fen()} (script bug)'
        san = board.san(move)
        self.get_logger().info(f'    move: {sc.uci} ({san})')

        # Decompose on the *pre-push* board, then fill world coordinates.
        raw_actions = self.brain.decompose(move)
        enriched = self.brain.with_coordinates(raw_actions)
        actions = [_enriched_dict_to_action(d) for d in enriched]

        self.get_logger().info(f'    plan: {len(actions)} piece action(s)')
        for i, a in enumerate(actions, start=1):
            self.get_logger().info(f'      [{i}/{len(actions)}] {describe_action(a)}')

        # Hand the ordered actions to the MoveIt executor (the physical loop).
        ok = self.executor_.execute(actions)
        if not ok:
            return False, 'executor reported failure (planning/execution)'

        # Advance the authoritative game state exactly like the real loop.
        self.brain.push(move)
        return True, f'executed {sc.uci} ({san}); board now {self.brain.fen}'

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the selected scenarios in order; return a process exit code."""
        scenarios = self._selected_scenarios(argv)
        self.get_logger().info(
            'play_sim_game: running '
            f'{len(scenarios)} scenario(s): {[s.name for s in scenarios]}')

        results: List[Tuple[str, bool, str]] = []
        for sc in scenarios:
            try:
                ok, msg = self._run_scenario(sc)
            except Exception as exc:  # noqa: BLE001 - keep going, report it
                self.get_logger().error(f'scenario {sc.name} raised: {exc}')
                ok, msg = False, f'exception: {exc}'
            tag = 'PASS' if ok else 'FAIL'
            self.get_logger().info(f'  [{tag}] {sc.name}: {msg}')
            results.append((sc.name, ok, msg))

        # -- final summary --------------------------------------------------
        n_pass = sum(1 for _, ok, _ in results if ok)
        n_total = len(results)
        self.get_logger().info('')
        self.get_logger().info('=== summary ===')
        for name, ok, msg in results:
            self.get_logger().info(f'  {"PASS" if ok else "FAIL"}  {name}')
        self.get_logger().info(f'  {n_pass}/{n_total} scenario(s) passed')
        return 0 if n_pass == n_total else 1


def main(args=None):
    """Build the runner, play the scripted scenarios, then shut down."""
    import threading
    from rclpy.executors import SingleThreadedExecutor

    rclpy.init(args=args)
    # ros2 run passes through extra positional args after the executable name;
    # rclpy.init strips its own --ros-args, leaving scenario tokens in argv.
    argv = [a for a in (args if args is not None else sys.argv[1:])]
    node = PlaySimGame()
    # Spin the node in a BACKGROUND thread so the MoveItExecutor's action-client
    # futures (goal acceptance + result) get serviced while run() blocks polling
    # them on the main thread. (The executor's _spin_until_complete intentionally
    # does not spin itself, to avoid nested-executor deadlocks.)
    spin_executor = SingleThreadedExecutor()
    spin_executor.add_node(node)
    spin_thread = threading.Thread(target=spin_executor.spin, daemon=True)
    spin_thread.start()
    exit_code = 1
    try:
        exit_code = node.run(argv)
    except KeyboardInterrupt:
        pass
    finally:
        spin_executor.shutdown()
        # NOTE: do not call executor_.close() here -- on MoveItExecutor that
        # CLOSES THE GRIPPER (a motion), not a resource teardown.  The action
        # clients are released when the node is destroyed.
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
