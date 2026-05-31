# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Game-loop orchestrator node (ROS 2, thin wrapper around the logic).

State machine (one turn per /human_move_done trigger)::

    WAIT_HUMAN  --(/human_move_done)-->  DETECT
    DETECT      vision  DetectChanges    -->  RESOLVE
    RESOLVE     brain   ResolveHumanMove -->  ENGINE
    ENGINE      brain   GetEngineMove    -->  PLAN          (stop if game_over)
    PLAN        brain   PlanPieceActions -->  EXECUTE
    EXECUTE     executor.execute(actions)-->  (publish post-engine FEN) -> VERIFY
    VERIFY      vision  DetectChanges (sanity re-read) -->  WAIT_HUMAN

The brain is the authoritative game state; vision only reports *changed
squares*; moves are resolved by matching changed squares to legal moves
(handled inside the brain's ResolveHumanMove).  Decomposition into physical
PieceActions is done by the brain's PlanPieceActions; this node simply hands the
resulting actions to the selected executor.

The node is intentionally thin -- all the testable orchestration logic lives in
:mod:`chess_arm_orchestrator.piece_actions` and is reused by the no-ROS dry-run.

DEADLOCK NOTE (do NOT reintroduce):
  The whole turn runs synchronously *inside* the /human_move_done service
  callback.  That callback must run on its OWN MutuallyExclusiveCallbackGroup,
  while the four downstream service clients (detect/resolve/engine/plan) live on
  a single shared ReentrantCallbackGroup, and the node is spun by a
  MultiThreadedExecutor with >= 4 threads.  This lets the executor service the
  reentrant client-response callbacks on *other* threads while the turn handler
  blocks polling its futures.  Crucially, ``_call_sync`` does NOT call
  ``rclpy.spin_until_future_complete`` (which would nest a spin inside the
  executor that is already spinning the node and deadlock); it polls
  ``future.done()`` with a small sleep instead.

CLOSED SIM LOOP:
  ``/sim_board_fen`` (std_msgs/String, transient_local/latched) carries the
  observed ground-truth FEN.  After a successful EXECUTE the orchestrator
  publishes the post-engine FEN (the ``.fen`` of the GetEngineMove response) so
  the ground truth and the vision stub track the arm having moved; the VERIFY
  DetectChanges then reports exactly the engine move's squares.
"""

from __future__ import annotations

import time
from enum import auto, Enum

from chess_arm_interfaces.srv import (
    DetectChanges,
    GetEngineMove,
    PlanPieceActions,
    ResolveHumanMove,
)
from chess_arm_orchestrator.executors import describe_action, make_executor
import rclpy
from rclpy.callback_groups import (
    MutuallyExclusiveCallbackGroup,
    ReentrantCallbackGroup,
)
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String
from std_srvs.srv import Trigger


class State(Enum):
    """States of the per-turn game loop."""

    WAIT_HUMAN = auto()
    DETECT = auto()
    RESOLVE = auto()
    ENGINE = auto()
    PLAN = auto()
    EXECUTE = auto()
    VERIFY = auto()
    GAME_OVER = auto()


# Service names (kept here so vision/brain bringup can match them).
SRV_DETECT = 'detect_changes'
SRV_RESOLVE = 'resolve_human_move'
SRV_ENGINE = 'get_engine_move'
SRV_PLAN = 'plan_piece_actions'

# Ground-truth board topic shared by the sim driver, vision, and this node.
SIM_BOARD_FEN_TOPIC = '/sim_board_fen'


class OrchestratorNode(Node):
    """ROS node that runs one game turn per /human_move_done trigger."""

    def __init__(self):
        super().__init__('chess_arm_orchestrator')

        # -- parameters -----------------------------------------------------
        self.declare_parameter('executor', 'dry_run')
        self.declare_parameter('service_timeout_sec', 10.0)
        self.declare_parameter('verify_after_move', True)
        self.declare_parameter('autostop_on_game_over', True)

        executor_name = self.get_parameter('executor').value
        self._timeout = float(self.get_parameter('service_timeout_sec').value)
        self._verify = bool(self.get_parameter('verify_after_move').value)
        self._autostop = bool(self.get_parameter('autostop_on_game_over').value)

        try:
            self._executor = make_executor(
                executor_name, logger=self.get_logger(), node=self)
        except ValueError as exc:
            self.get_logger().error(str(exc))
            raise
        self.get_logger().info(f'executor = {executor_name}')

        self._state = State.WAIT_HUMAN
        self._busy = False

        # -- callback groups ------------------------------------------------
        # The four downstream service clients share ONE ReentrantCallbackGroup
        # so their async-call response callbacks can be serviced on any spare
        # executor thread while the turn handler is busy polling a future.
        self._client_cb = ReentrantCallbackGroup()
        # The /human_move_done service runs the whole turn synchronously; it
        # must live on its OWN MutuallyExclusiveCallbackGroup so the turn body
        # never blocks the response callbacks above (and so two triggers cannot
        # interleave on the same group).
        self._trigger_cb = MutuallyExclusiveCallbackGroup()

        # -- service clients (vision + brain) ------------------------------
        self._cli_detect = self.create_client(
            DetectChanges, SRV_DETECT, callback_group=self._client_cb)
        self._cli_resolve = self.create_client(
            ResolveHumanMove, SRV_RESOLVE, callback_group=self._client_cb)
        self._cli_engine = self.create_client(
            GetEngineMove, SRV_ENGINE, callback_group=self._client_cb)
        self._cli_plan = self.create_client(
            PlanPieceActions, SRV_PLAN, callback_group=self._client_cb)

        # -- ground-truth FEN publisher (latched) ---------------------------
        # transient_local so a late-joining vision/driver still receives the
        # most recent post-move FEN; matches the subscriber/driver latched QoS.
        fen_qos = QoSProfile(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._fen_pub = self.create_publisher(
            String, SIM_BOARD_FEN_TOPIC, fen_qos)

        # -- trigger service (own group) -----------------------------------
        self._trigger_srv = self.create_service(
            Trigger, 'human_move_done', self._on_human_move_done,
            callback_group=self._trigger_cb)

        self.get_logger().info(
            'orchestrator up -- call /human_move_done after each human move '
            f'(state={self._state.name})')

    # -- helpers ------------------------------------------------------------

    def _call_sync(self, client, request, label: str):
        """Block-call a service from within the trigger callback thread.

        We do NOT spin here.  The node is being serviced by the orchestrator's
        MultiThreadedExecutor, and the clients live on a ReentrantCallbackGroup,
        so the executor delivers the response on another thread while we poll
        ``future.done()``.  Calling ``rclpy.spin_until_future_complete`` instead
        would nest a spin inside the already-spinning executor and deadlock.
        """
        if not client.wait_for_service(timeout_sec=self._timeout):
            self.get_logger().error(f'{label}: service unavailable')
            return None
        future = client.call_async(request)
        deadline = time.monotonic() + self._timeout
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not future.done():
            self.get_logger().error(f'{label}: timed out')
            return None
        return future.result()

    def _publish_fen(self, fen: str) -> None:
        """Latch the post-engine ground-truth FEN onto /sim_board_fen."""
        fen = (fen or '').strip()
        if not fen:
            self.get_logger().warning(
                'post-engine FEN empty -- not publishing /sim_board_fen')
            return
        msg = String()
        msg.data = fen
        self._fen_pub.publish(msg)
        self.get_logger().info(f'published post-engine FEN: {fen}')

    # -- trigger entry point ------------------------------------------------

    def _on_human_move_done(self, request, response):
        if self._busy:
            response.success = False
            response.message = 'busy: a turn is already in progress'
            return response
        if self._state == State.GAME_OVER:
            response.success = False
            response.message = 'game over -- restart the node to play again'
            return response

        self._busy = True
        try:
            ok, msg = self._run_turn()
        except Exception as exc:  # noqa: BLE001 - never crash the service
            self.get_logger().error(f'turn failed: {exc}')
            ok, msg = False, f'exception: {exc}'
        finally:
            self._busy = False
        response.success = ok
        response.message = msg
        return response

    # -- the state machine for one turn ------------------------------------

    def _run_turn(self):
        # DETECT --------------------------------------------------------
        self._state = State.DETECT
        det = self._call_sync(self._cli_detect, DetectChanges.Request(), 'DETECT')
        if det is None or not det.ok:
            return False, 'DETECT failed'
        changed = list(det.changed_squares)
        self.get_logger().info(f'DETECT: changed squares = {changed}')

        # RESOLVE -------------------------------------------------------
        self._state = State.RESOLVE
        rreq = ResolveHumanMove.Request()
        rreq.changed_squares = changed
        res = self._call_sync(self._cli_resolve, rreq, 'RESOLVE')
        if res is None or not res.ok:
            why = res.message if res is not None else 'no response'
            return False, f'RESOLVE failed: {why}'
        self.get_logger().info(f'RESOLVE: human move = {res.uci} ({res.san})')

        # ENGINE --------------------------------------------------------
        self._state = State.ENGINE
        eng = self._call_sync(self._cli_engine, GetEngineMove.Request(), 'ENGINE')
        if eng is None or not eng.ok:
            return False, 'ENGINE failed'
        if eng.game_over:
            self.get_logger().info(
                f'GAME OVER after human move: {eng.result} ({eng.fen})')
            # Still publish the FEN so vision/ground-truth reflect the human's
            # mating/stalemating move.
            self._publish_fen(eng.fen)
            if self._autostop:
                self._state = State.GAME_OVER
            return True, f'game over: {eng.result}'
        self.get_logger().info(f'ENGINE: reply = {eng.uci} ({eng.san})')

        # PLAN ----------------------------------------------------------
        self._state = State.PLAN
        preq = PlanPieceActions.Request()
        preq.uci = eng.uci
        plan = self._call_sync(self._cli_plan, preq, 'PLAN')
        if plan is None or not plan.ok:
            why = plan.message if plan is not None else 'no response'
            return False, f'PLAN failed: {why}'
        actions = list(plan.actions)
        self.get_logger().info(f'PLAN: {len(actions)} piece action(s)')
        for i, action in enumerate(actions, start=1):
            self.get_logger().info(f'  [{i}] {describe_action(action)}')

        # EXECUTE -------------------------------------------------------
        self._state = State.EXECUTE
        if not self._executor.execute(actions):
            return False, 'EXECUTE failed'

        # Publish the post-engine ground-truth FEN so the closed sim loop tracks
        # the arm having moved.  This MUST happen after a successful EXECUTE and
        # before VERIFY, so the VERIFY DetectChanges reports the engine move's
        # squares.
        self._publish_fen(eng.fen)

        # VERIFY (re-read the board to confirm our own placement) -------
        if self._verify:
            self._state = State.VERIFY
            ver = self._call_sync(
                self._cli_detect, DetectChanges.Request(), 'VERIFY')
            if ver is None or not ver.ok:
                self.get_logger().warning('VERIFY: re-read failed (continuing)')
            else:
                self.get_logger().info(
                    'VERIFY: post-move changed squares = '
                    f'{list(ver.changed_squares)}')

        # GAME_OVER check after engine's own move ----------------------
        # GetEngineMove already reported eng.game_over for the position AFTER the
        # engine move, so trust that flag rather than issuing a second engine
        # call (which could make the brain play again).
        if eng.game_over:
            self.get_logger().info(f'GAME OVER: {eng.result}')
            if self._autostop:
                self._state = State.GAME_OVER
            return True, f'engine move done; game over: {eng.result}'

        self._state = State.WAIT_HUMAN
        return True, f'engine played {eng.uci}; awaiting next human move'


def main(args=None):
    """Spin the orchestrator node under a multi-threaded executor.

    At least 4 threads: one can be parked inside the /human_move_done turn
    handler while the others service the reentrant client-response callbacks the
    turn is waiting on.  Fewer threads can starve those responses and deadlock.
    """
    rclpy.init(args=args)
    node = OrchestratorNode()
    from rclpy.executors import MultiThreadedExecutor

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
