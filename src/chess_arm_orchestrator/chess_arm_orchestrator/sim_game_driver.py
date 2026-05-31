# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Drive the LIVE game loop by playing the HUMAN side of a scripted game.

This node closes the Phase-0 sim loop end-to-end.  It plays White (the human)
against the engine (Black, driven by the orchestrator + brain) over the ROS
service graph:

    sim_game_driver (HUMAN)            orchestrator (state machine)
    -----------------------            ----------------------------
    publish post-human FEN  --latched--> vision sees it
    call /human_move_done   ----------->  DETECT  (human-move squares)
                                          RESOLVE (push human move on brain)
                                          ENGINE  (push engine reply)
                                          PLAN + EXECUTE (arm moves in sim)
                                          publish post-engine FEN  --latched-->
                                          VERIFY  (engine-move squares)
    <----- Trigger response ------------  return
    (read latest post-engine FEN, push the next scripted human move, repeat)

The closed loop keeps three views of the board consistent:

* ``/sim_board_fen`` is a latched (transient_local) ``std_msgs/String`` carrying
  the *observed* ground-truth FEN.  This driver and the orchestrator are the two
  publishers; vision_node and this driver are the subscribers.
* This driver owns the HUMAN ply: it loads the latest observed FEN into a
  ``chess.Board``, pushes the scripted human move, and publishes the result --
  so vision's next DetectChanges reports exactly the human-move squares.
* The orchestrator owns the ENGINE ply and re-publishes the post-engine FEN, so
  this driver's next iteration loads a board that already reflects the arm's
  move.

Because the engine's reply is not deterministic (movetime/elo limited), a fixed
scripted human move can become illegal after an unexpected reply.  When that
happens the driver falls back to a deterministic legal move (and logs it) so the
multi-turn loop stays CONTINUOUS rather than crashing.  The default opening
develops into the centre, which reliably yields at least one engine capture.

Concurrency: the node is spun in a BACKGROUND thread (SingleThreadedExecutor) so
the subscription callback latches incoming FENs and the ``/human_move_done``
client future is serviced while the main loop polls it.  The main loop NEVER
nested-spins.

Run it (with the live stack up -- see live_game.launch.py)::

    ros2 launch chess_arm_orchestrator live_game.launch.py
    # the launch starts this driver automatically; or run it standalone:
    ros2 run chess_arm_orchestrator sim_game_driver
    ros2 run chess_arm_orchestrator sim_game_driver e2e4 g1f3 f1c4 b1c3 d2d4
    ros2 run chess_arm_orchestrator sim_game_driver --ros-args \
        -p moves:='[e2e4, g1f3, f1c4, b1c3, d2d4]'
"""

from __future__ import annotations

import sys
import threading
import time
from typing import List, Optional, Sequence

import chess
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String
from std_srvs.srv import Trigger

# Standard chess starting position.
START_FEN = chess.STARTING_FEN

TOPIC_SIM_FEN = "/sim_board_fen"
SRV_HUMAN_MOVE_DONE = "/human_move_done"

# Default scripted human (White) opening.  Sound developing moves that open the
# centre; against an engine reply this line reliably produces at least one
# engine capture within a few plies.  Each move is legality-checked before it is
# pushed (see _next_human_move) so the loop is robust to engine deviations.
DEFAULT_MOVES: List[str] = ["e2e4", "g1f3", "f1c4", "b1c3", "d2d4"]


def _latched_qos() -> QoSProfile:
    """Transient-local, keep-last(1), reliable -- the latched FEN contract."""
    return QoSProfile(
        depth=1,
        history=HistoryPolicy.KEEP_LAST,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )


class SimGameDriver(Node):
    """Plays the HUMAN side of a scripted game to drive the live loop."""

    def __init__(self) -> None:
        super().__init__("sim_game_driver")

        # -- parameters -----------------------------------------------------
        self.declare_parameter("moves", DEFAULT_MOVES)
        self.declare_parameter("start_fen", START_FEN)
        # Per-turn timeout for the /human_move_done round-trip (covers DETECT
        # -> RESOLVE -> ENGINE -> PLAN -> EXECUTE -> VERIFY incl. real motion).
        self.declare_parameter("turn_timeout_sec", 120.0)
        self.declare_parameter("service_wait_sec", 30.0)
        # How long to wait for the first latched FEN before each human move.
        self.declare_parameter("fen_wait_sec", 10.0)

        self._start_fen = (
            self.get_parameter("start_fen").get_parameter_value().string_value
            or START_FEN
        )
        self._turn_timeout = float(self.get_parameter("turn_timeout_sec").value)
        self._service_wait = float(self.get_parameter("service_wait_sec").value)
        self._fen_wait = float(self.get_parameter("fen_wait_sec").value)

        # -- latest observed FEN (latched by the subscription callback) ----
        self._lock = threading.Lock()
        self._latest_fen: Optional[str] = None

        # -- publisher + subscriber on the latched FEN topic ----------------
        self._fen_pub = self.create_publisher(
            String, TOPIC_SIM_FEN, _latched_qos())
        self._fen_sub = self.create_subscription(
            String, TOPIC_SIM_FEN, self._on_fen, _latched_qos())

        # -- /human_move_done client ---------------------------------------
        self._trigger_cli = self.create_client(Trigger, SRV_HUMAN_MOVE_DONE)

        self.get_logger().info(
            "sim_game_driver up: publishing/subscribing %s (latched), "
            "client of %s" % (TOPIC_SIM_FEN, SRV_HUMAN_MOVE_DONE)
        )

    # ------------------------------------------------------------------ #
    # Subscription: latch the latest observed board FEN (engine + human plies).
    # ------------------------------------------------------------------ #
    def _on_fen(self, msg: String) -> None:
        fen = msg.data.strip()
        if not fen:
            return
        with self._lock:
            self._latest_fen = fen

    def _get_latest_fen(self) -> Optional[str]:
        with self._lock:
            return self._latest_fen

    # ------------------------------------------------------------------ #
    # Move scripting.
    # ------------------------------------------------------------------ #
    def _scripted_moves(self, argv: Optional[Sequence[str]]) -> List[str]:
        """Resolve the scripted human UCI moves: argv > ROS param > default."""
        tokens: List[str] = []
        if argv:
            tokens = [t.strip() for t in argv if t and not t.startswith("-")]
        if not tokens:
            param = self.get_parameter("moves").value
            if isinstance(param, (list, tuple)):
                tokens = [str(t).strip() for t in param if str(t).strip()]
            elif param is not None and str(param).strip():
                tokens = [str(param).strip()]
        if not tokens:
            tokens = list(DEFAULT_MOVES)
        return tokens

    @staticmethod
    def _next_human_move(board: chess.Board, scripted_uci: str) -> chess.Move:
        """Return the scripted move if legal, else a deterministic legal move.

        Keeps the multi-turn loop continuous when the engine deviates from the
        line the script assumed.  Falls back to the lexicographically-first
        legal UCI move (deterministic, never None for a non-terminal position).
        """
        try:
            mv = chess.Move.from_uci(scripted_uci)
        except ValueError:
            mv = None
        if mv is not None and mv in board.legal_moves:
            return mv
        legal = sorted(board.legal_moves, key=lambda m: m.uci())
        return legal[0]

    # ------------------------------------------------------------------ #
    # Latched-FEN wait + Trigger round-trip (NO nested spin).
    # ------------------------------------------------------------------ #
    def _await_latest_fen(self) -> Optional[str]:
        """Block until a latched FEN has arrived (or fen_wait elapses)."""
        deadline = time.monotonic() + self._fen_wait
        while time.monotonic() < deadline:
            fen = self._get_latest_fen()
            if fen is not None:
                return fen
            time.sleep(0.02)
        return self._get_latest_fen()

    def _call_human_move_done(self) -> Optional[Trigger.Response]:
        """Call /human_move_done and poll the future (executor spins us)."""
        if not self._trigger_cli.wait_for_service(timeout_sec=self._service_wait):
            self.get_logger().error(
                f"{SRV_HUMAN_MOVE_DONE} unavailable after "
                f"{self._service_wait:.0f}s -- is the orchestrator up?")
            return None
        future = self._trigger_cli.call_async(Trigger.Request())
        deadline = time.monotonic() + self._turn_timeout
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not future.done():
            self.get_logger().error(
                f"{SRV_HUMAN_MOVE_DONE} timed out after "
                f"{self._turn_timeout:.0f}s")
            return None
        return future.result()

    # ------------------------------------------------------------------ #
    # The game.
    # ------------------------------------------------------------------ #
    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        moves = self._scripted_moves(argv)
        self.get_logger().info(
            f"sim_game_driver: scripted human moves = {moves}")

        # Wait for the orchestrator before seeding the board so we never publish
        # a starting FEN into the void (vision is latched, but the orchestrator
        # turn service is the gate for a turn).
        if not self._trigger_cli.wait_for_service(timeout_sec=self._service_wait):
            self.get_logger().error(
                f"{SRV_HUMAN_MOVE_DONE} unavailable after "
                f"{self._service_wait:.0f}s -- aborting")
            return 1

        # Seed the ground-truth board with the standard starting position.
        self._publish_fen(self._start_fen, "starting")
        # Make sure our own latched publish (and any pre-existing one) lands.
        seeded = self._await_latest_fen()
        if seeded is None:
            self.get_logger().warning(
                "no latched FEN observed after seeding; proceeding with "
                f"start_fen={self._start_fen}")
            seeded = self._start_fen

        played = 0
        captures_by_engine = 0
        result = "*"

        for turn_idx, scripted in enumerate(moves, start=1):
            latest = self._await_latest_fen() or seeded
            try:
                board = chess.Board(latest)
            except ValueError as exc:
                self.get_logger().error(
                    f"turn {turn_idx}: latest FEN invalid ({exc}); stopping")
                break

            if board.is_game_over():
                result = board.result()
                self.get_logger().info(
                    f"turn {turn_idx}: game already over ({result}); stopping")
                break

            move = self._next_human_move(board, scripted)
            san = board.san(move)
            used_fallback = move.uci() != scripted
            note = " (FALLBACK; scripted move illegal here)" if used_fallback else ""
            self.get_logger().info(
                f"--- turn {turn_idx}/{len(moves)}: human plays "
                f"{move.uci()} ({san}){note} ---")

            board.push(move)
            post_human_fen = board.fen()
            self._publish_fen(post_human_fen, f"post-human turn {turn_idx}")

            # If the human move itself ended the game, the orchestrator will
            # report game_over after its ENGINE step; still trigger one turn so
            # the orchestrator can settle and report.
            resp = self._call_human_move_done()
            if resp is None:
                self.get_logger().error(
                    f"turn {turn_idx}: /human_move_done failed; stopping")
                break
            played += 1
            self.get_logger().info(
                f"turn {turn_idx}: orchestrator -> success={resp.success} "
                f"msg='{resp.message}'")

            # Read the post-engine board the orchestrator just published.
            post_engine_fen = self._await_latest_fen() or post_human_fen
            try:
                post_board = chess.Board(post_engine_fen)
            except ValueError:
                post_board = None

            if post_board is not None:
                # Did the engine ply (the last move on the post-engine board) a
                # capture?  Compare occupancy counts human-vs-engine board.
                try:
                    human_board = chess.Board(post_human_fen)
                    n_after = len(post_board.piece_map())
                    n_before = len(human_board.piece_map())
                    if n_after < n_before:
                        captures_by_engine += 1
                        self.get_logger().info(
                            f"turn {turn_idx}: engine reply was a CAPTURE "
                            f"(pieces {n_before} -> {n_after})")
                except ValueError:
                    pass

            if not resp.success:
                # The orchestrator reports failure on a real EXECUTE/PLAN error
                # OR a benign 'game over' (success=True there).  A False here is
                # a genuine stop condition.
                self.get_logger().warning(
                    f"turn {turn_idx}: orchestrator reported failure -- stopping")
                break

            if "game over" in (resp.message or "").lower():
                self.get_logger().info(
                    f"turn {turn_idx}: orchestrator reports game over; stopping")
                if post_board is not None and post_board.is_game_over():
                    result = post_board.result()
                break

        # -- final summary --------------------------------------------------
        final_fen = self._get_latest_fen() or seeded
        self.get_logger().info("")
        self.get_logger().info("=== sim_game_driver summary ===")
        self.get_logger().info(f"  full turns played : {played}/{len(moves)}")
        self.get_logger().info(f"  engine captures    : {captures_by_engine}")
        self.get_logger().info(f"  final result       : {result}")
        self.get_logger().info(f"  final FEN          : {final_fen}")
        # Phase-0 success: at least one full multi-turn loop completed.
        return 0 if played > 0 else 1

    def _publish_fen(self, fen: str, label: str) -> None:
        msg = String()
        msg.data = fen
        self._fen_pub.publish(msg)
        # Mirror our own publish into the latch immediately so the very next
        # _await_latest_fen() sees it even before the subscription callback runs.
        with self._lock:
            self._latest_fen = fen
        self.get_logger().info(f"published {label} FEN: {fen}")


def main(args=None) -> int:
    """Spin the driver in a background thread; play the scripted game inline."""
    from rclpy.utilities import remove_ros_args

    rclpy.init(args=args)
    # Strip ROS args (--ros-args, remaps like __node:=, --params-file <path>, ...)
    # so only genuine positional move tokens remain. When launched via a launch
    # file there are none, and _scripted_moves falls back to the 'moves' param /
    # DEFAULT_MOVES (the previous code mistook __node:= and the params path for moves).
    raw = list(args) if args is not None else list(sys.argv)
    argv = remove_ros_args(args=raw)[1:]
    node = SimGameDriver()

    # Background spin so the FEN subscription latches and the Trigger client
    # future is serviced while run() polls it on the main thread (no nested
    # spin -- mirrors play_sim_game's pattern).
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
        # Stop the background spin and JOIN before destroying the node, else the
        # spin thread can touch a half-destroyed node and segfault on shutdown.
        spin_executor.shutdown()
        spin_thread.join(timeout=3.0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
