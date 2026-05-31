"""chess_arm_vision -- Phase-0 move-detection stub + per-square diff library.

The ENGINE (chess_arm_brain) is the authoritative game state. Vision never
*names* the piece type to the brain; it only reports which board squares
CHANGED between two observations. The brain then matches that change-set
against the legal moves (python-chess) to resolve the actual move.

Public API:
    detector.changed_squares(before_fen, after_fen) -> list[str]
        Pure-Python (no ROS, no python-chess). The single source of truth for
        what a per-square diff produces; unit-testable in isolation.
"""

from chess_arm_vision.detector import changed_squares

__all__ = ["changed_squares"]
