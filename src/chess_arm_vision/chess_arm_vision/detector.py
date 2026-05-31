"""Pure-Python per-square board diff (NO ROS, NO python-chess dependency).

This module is the importable logic core of chess_arm_vision. It mirrors what a
real per-square overhead-camera diff produces: given two board observations
expressed as FEN strings, it returns the sorted list of algebraic squares
(a1..h8) whose CONTENTS differ between the two observations.

WHAT "DIFFERS" MEANS HERE (read carefully -- this is the crux of the project)
---------------------------------------------------------------------------
A square is reported as changed when its appearance toggles between the two
frames. That covers three transitions:

  * empty  -> occupied   (a piece arrived)
  * occupied -> empty     (a piece left)
  * occupied -> occupied with a *different* piece there (a capture: the colour
    /piece on the destination square visibly changed)

That third case is exactly why a capture must report TWO squares and not one:
the attacker's source square goes occupied->empty, and the destination square
changes from the defender's piece to the attacker's piece. A fixed overhead
camera DOES see that destination change -- the square's colour/contents flip --
even though it cannot *name* either piece.

This is the key distinction the project memory draws: we do NOT classify piece
TYPE (we never tell the brain "a black knight moved"). We only emit the set of
squares that visibly changed. The brain then resolves the change-set against the
legal-move list. So the diff is identity-aware at the per-square level (did this
square's contents change?) but never reports the identities themselves.

Resulting change-set sizes, which the brain relies on:
  * quiet move (e2e4)      -> 2 squares  {from, to}
  * capture   (exd5)        -> 2 squares  {from, to}
  * castling  (O-O / O-O-O) -> 4 squares  {king from/to, rook from/to}
  * en passant (e5d6)       -> 3 squares  {from, to, captured-pawn square}
  * promotion (e7e8q)       -> 2 squares  {from, to}
  * promotion + capture     -> 2 squares  {from, to}

FEN reference: only the FIRST field (piece placement) is used. It encodes ranks
8..1 separated by '/', each rank file a..h left-to-right, digits = run of empty
squares, letters = pieces (case = colour).
"""

from __future__ import annotations

from typing import Dict, Set

# Files a..h and ranks 1..8 in algebraic notation.
FILES = "abcdefgh"
RANKS = "12345678"


def board_map(fen: str) -> Dict[str, str]:
    """Return {square: piece_char} for every OCCUPIED square in `fen`.

    Only the piece-placement field (the part before the first space) matters.
    Accepts a bare placement field too (no spaces). Empty squares are simply
    absent from the returned mapping.

    Raises ValueError if the placement field is malformed (wrong number of
    ranks, or a rank that does not sum to exactly 8 files).
    """
    if fen is None:
        raise ValueError("fen is None")

    placement = fen.strip().split(" ", 1)[0]
    rank_rows = placement.split("/")
    if len(rank_rows) != 8:
        raise ValueError(
            f"FEN placement must have 8 ranks, got {len(rank_rows)}: {placement!r}"
        )

    pieces: Dict[str, str] = {}
    # FEN lists rank 8 first, rank 1 last.
    for row, rank_char in zip(rank_rows, reversed(RANKS)):
        file_index = 0
        for ch in row:
            if ch.isdigit():
                file_index += int(ch)
            else:
                if file_index >= 8:
                    raise ValueError(
                        f"FEN rank overflows 8 files: {row!r} in {placement!r}"
                    )
                pieces[f"{FILES[file_index]}{rank_char}"] = ch
                file_index += 1
        if file_index != 8:
            raise ValueError(
                f"FEN rank does not fill 8 files (got {file_index}): "
                f"{row!r} in {placement!r}"
            )
    return pieces


def occupied_squares(fen: str) -> Set[str]:
    """Return the set of squares occupied by any piece in `fen`."""
    return set(board_map(fen).keys())


def changed_squares(before_fen: str, after_fen: str) -> list:
    """Sorted list of squares whose CONTENTS changed between two positions.

    A square is "changed" iff what sits on it differs between the two
    observations -- empty<->occupied, OR occupied by a *different* piece (a
    capture). This is the canonical per-square diff and is exactly the
    `changed_squares` payload the brain (ResolveHumanMove) consumes; the brain
    matches it against the legal moves without ever being told the piece types.

    The function is symmetric in its two arguments.

    Change-set sizes: quiet=2, capture=2, castling=4, en passant=3,
    promotion=2.
    """
    before = board_map(before_fen)
    after = board_map(after_fen)
    all_squares = set(before) | set(after)
    # before.get / after.get yield None for an empty square, so an
    # empty<->occupied transition and a piece<->different-piece transition are
    # both caught, while an unchanged occupied square (same piece) is not.
    return sorted(sq for sq in all_squares if before.get(sq) != after.get(sq))
