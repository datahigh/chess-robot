"""chess_arm_brain: game/logic library + thin ROS 2 node for the chess robot arm.

The authoritative game state lives here (a ``chess.Board``). Vision only ever
reports *changed squares*; the move is resolved by matching that observed set
against the legal moves of the current position (never by classifying piece
type from vision).

The pure-Python pieces (``ChessBrain``, ``StockfishEngine``,
``BoardCoordinates``) carry no ROS dependency so they can be unit-tested with
plain ``pytest``. ``brain_node`` is a thin rclpy wrapper.
"""

from chess_arm_brain.brain import (  # noqa: F401
    ACTION_PICK_PLACE,
    ACTION_CLEAR_CAPTURE,
    ACTION_MOVE_ROOK,
    ACTION_CLEAR_EN_PASSANT,
    ACTION_REMOVE_PROMOTED_PAWN,
    ACTION_PLACE_PROMOTION,
    ACTION_NAMES,
    BoardCoordinates,
    ChessBrain,
    PROMOTION_QUEEN_SOURCE,
    StockfishEngine,
)

__all__ = [
    "ACTION_PICK_PLACE",
    "ACTION_CLEAR_CAPTURE",
    "ACTION_MOVE_ROOK",
    "ACTION_CLEAR_EN_PASSANT",
    "ACTION_REMOVE_PROMOTED_PAWN",
    "ACTION_PLACE_PROMOTION",
    "ACTION_NAMES",
    "BoardCoordinates",
    "ChessBrain",
    "PROMOTION_QUEEN_SOURCE",
    "StockfishEngine",
]
