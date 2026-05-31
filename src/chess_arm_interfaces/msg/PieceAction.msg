# A single primitive manipulation step the arm must perform to realise one chess
# move. The brain decomposes a UCI move (computed on the board state BEFORE the
# move is pushed) into an ordered list of these. World coordinates (from_xyz /
# to_xyz) come from chess_arm_description/config/board_coordinates.yaml; pick at
# grasp height, lift, traverse, place, retract is the responsibility of MoveIt.

# --- action_type constants ---
uint8 PICK_PLACE=0           # move a piece from from_square to to_square
uint8 CLEAR_CAPTURE=1        # remove the piece on to_square to a graveyard slot
uint8 MOVE_ROOK=2            # second leg of a castle: relocate the rook
uint8 CLEAR_EN_PASSANT=3     # remove the en-passant-captured pawn (behind to_square)
uint8 REMOVE_PROMOTED_PAWN=4 # remove the promoting pawn to a graveyard slot
uint8 PLACE_PROMOTION=5      # fetch the promoted piece from graveyard onto to_square

uint8 action_type

# Algebraic squares (e.g. "e2", "e4") or graveyard slot ids (e.g. "GY1").
# Either may be a board square or a graveyard slot depending on action_type.
string from_square
string to_square

# World-frame Cartesian targets (metres) looked up from board_coordinates.yaml.
geometry_msgs/Point from_xyz
geometry_msgs/Point to_xyz

# Optional piece hint, e.g. "Q" for the promotion piece placed by PLACE_PROMOTION.
# Empty for actions where the piece identity is irrelevant to the motion.
string piece
