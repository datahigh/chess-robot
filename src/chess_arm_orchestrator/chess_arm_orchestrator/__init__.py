# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""chess_arm_orchestrator: game-loop state machine + pluggable executor.

The orchestration *logic* (move -> PieceAction decomposition, graveyard slot
allocation, board-coordinate lookups) lives in
:mod:`chess_arm_orchestrator.piece_actions` and is pure Python so it can be
unit-tested and dry-run without ROS.  The ROS node
(:mod:`chess_arm_orchestrator.orchestrator_node`) is a thin wrapper.
"""
