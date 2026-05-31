"""Phase-0 vision node (move-detection STUB).

Real OpenCV comes later. For Phase 0 the "camera" is the simulator's
ground-truth FEN, published on /sim_board_fen (std_msgs/String). This node:

  * subscribes to /sim_board_fen (latched / transient_local QoS) and remembers
    the most recently observed FEN;
  * remembers the *last-observed* FEN (the "before" snapshot);
  * serves DetectChanges by diffing the last-observed-vs-current observed FEN
    via chess_arm_vision.detector.changed_squares and returning the change-set
    plus the current FEN, THEN advances last-observed to current.

This mirrors the real capture-before / capture-after diff flow exactly, without
any image processing: each DetectChanges reports exactly the squares that
changed since the previous DetectChanges, then re-arms the baseline.  In the
closed sim loop:

  * the sim_game_driver publishes the post-human FEN, then triggers a turn;
  * the orchestrator's DETECT reports the human-move squares;
  * the orchestrator EXECUTEs the engine reply and publishes the post-engine
    FEN, so the orchestrator's VERIFY DetectChanges reports the engine-move
    squares.

Because both transitions advance the baseline, consecutive DetectChanges calls
each report exactly one move worth of changes.

QoS: the publisher (sim_game_driver / orchestrator) is transient_local
(latched), so this subscription is too -- otherwise a sample published before
this node connected would be missed.

The heavy logic lives in detector.py (pure Python, unit-tested); this node is a
thin ROS wrapper.
"""

from __future__ import annotations

import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String

from chess_arm_interfaces.srv import DetectChanges

from chess_arm_vision.detector import board_map, changed_squares

# Standard chess starting position (placement field is all we ever read).
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _latched_qos() -> QoSProfile:
    """Transient-local, keep-last(1), reliable -- match the latched publisher."""
    return QoSProfile(
        depth=1,
        history=HistoryPolicy.KEEP_LAST,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )


class VisionNode(Node):
    """Phase-0 stub: turns ground-truth FEN observations into per-square diffs."""

    def __init__(self) -> None:
        super().__init__("vision_node")

        # Allow the operator to seed the baseline observation (defaults to the
        # standard opening). Useful so the very first DetectChanges after a
        # board reset diffs against the start position rather than nothing.
        self.declare_parameter("initial_fen", START_FEN)
        initial_fen = (
            self.get_parameter("initial_fen").get_parameter_value().string_value
        )

        # _prev_fen: the last-observed snapshot ("before"); _current_fen: latest
        # observation ("after"). Guarded by a lock because the subscription
        # callback and the service callback can run on different threads.
        self._lock = threading.Lock()
        self._prev_fen = initial_fen
        self._current_fen = initial_fen

        # Validate the seed up front so misconfiguration fails loudly.
        try:
            board_map(initial_fen)
        except ValueError as exc:
            self.get_logger().error(f"Invalid initial_fen, using start: {exc}")
            self._prev_fen = START_FEN
            self._current_fen = START_FEN

        # Transient-local QoS so a latched FEN published before we connected is
        # still delivered (the publisher is the sim_game_driver/orchestrator,
        # both transient_local). Depth 1, keep-last: the FEN is state.
        self._fen_sub = self.create_subscription(
            String, "/sim_board_fen", self._on_fen, _latched_qos()
        )
        self._detect_srv = self.create_service(
            DetectChanges, "detect_changes", self._on_detect_changes
        )

        self.get_logger().info(
            "vision_node (Phase-0 stub) up: subscribing /sim_board_fen "
            "(transient_local), serving detect_changes."
        )

    # ------------------------------------------------------------------ #
    # Subscription: latch the latest observed board FEN.
    # ------------------------------------------------------------------ #
    def _on_fen(self, msg: String) -> None:
        fen = msg.data.strip()
        if not fen:
            return
        try:
            board_map(fen)  # validate placement field only
        except ValueError as exc:
            self.get_logger().warn(f"Ignoring malformed /sim_board_fen: {exc}")
            return
        with self._lock:
            self._current_fen = fen

    # ------------------------------------------------------------------ #
    # Service: report the squares that changed since the last-observed FEN,
    # then advance last-observed to current so the next call diffs against this
    # observation.
    # ------------------------------------------------------------------ #
    def _on_detect_changes(self, request, response):  # noqa: ARG002 (empty req)
        with self._lock:
            before = self._prev_fen
            after = self._current_fen
            # Advance the baseline: the current observation becomes the next
            # "before". Successive DetectChanges calls then report each turn's
            # delta, matching the capture-before/after flow.
            self._prev_fen = after

        try:
            changes = changed_squares(before, after)
        except ValueError as exc:
            response.ok = False
            response.changed_squares = []
            response.fen = after
            self.get_logger().error(f"detect_changes diff failed: {exc}")
            return response

        response.ok = True
        response.changed_squares = changes
        response.fen = after
        self.get_logger().info(
            f"detect_changes: {len(changes)} changed square(s): {changes}"
        )
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
