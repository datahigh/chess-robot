"""Pure (no-ROS) unit tests for the per-square diff library.

These run under bare `pytest` -- they do not import rclpy. python-chess is used
only to *generate* the before/after FENs from real moves, so the test data
stays honest (we never hand-craft FENs that could drift from legal play). If
python-chess is unavailable the whole module is skipped.

Required change-set sizes verified here: quiet=2, capture=2, castling=4,
en passant=3.
"""

import pytest

chess = pytest.importorskip("chess")

from chess_arm_vision.detector import (
    board_map,
    changed_squares,
    occupied_squares,
)


def _step(board, uci):
    """Return (before_fen, after_fen) for playing `uci` on `board` (mutates)."""
    before = board.fen()
    board.push(chess.Move.from_uci(uci))
    after = board.fen()
    return before, after


def test_quiet_pawn_push_e2e4():
    board = chess.Board()  # standard start
    before, after = _step(board, "e2e4")
    assert changed_squares(before, after) == ["e2", "e4"]


def test_quiet_knight_move():
    board = chess.Board()
    before, after = _step(board, "g1f3")
    assert changed_squares(before, after) == ["f3", "g1"]


def test_capture_two_squares():
    # 1.e4 d5 2.exd5 -- the capture exd5. Source e4 goes empty; destination d5
    # changes from the black pawn to the white pawn (a visible per-square
    # change). A pure per-square diff therefore reports exactly two squares.
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("d7d5")
    before, after = _step(board, "e4d5")
    changed = changed_squares(before, after)
    assert changed == sorted(["e4", "d5"])
    assert len(changed) == 2


def test_castling_kingside_four_squares():
    # Clear the king-side for white, then O-O (e1g1). King e1->g1, rook h1->f1.
    board = chess.Board()
    for uci in ("g1f3", "a7a6", "e2e4", "b7b6", "f1c4", "c7c6"):
        board.push_uci(uci)
    before, after = _step(board, "e1g1")
    changed = changed_squares(before, after)
    assert changed == sorted(["e1", "g1", "h1", "f1"])
    assert len(changed) == 4


def test_castling_queenside_four_squares():
    # Position with white queen-side cleared, king still on e1 -> O-O-O (e1c1).
    # King e1->c1, rook a1->d1.
    board = chess.Board(
        "r1bqkbnr/pppppppp/n7/8/3P1B2/2N5/PPPQPPPP/R3KBNR w KQkq - 0 1"
    )
    before, after = _step(board, "e1c1")
    changed = changed_squares(before, after)
    assert changed == sorted(["e1", "c1", "a1", "d1"])
    assert len(changed) == 4


def test_en_passant_three_squares():
    # White pawn reaches e5, black replies ...d7d5, white takes en passant exd6.
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("a7a6")
    board.push_uci("e4e5")
    board.push_uci("d7d5")  # creates the en-passant target on d6
    before, after = _step(board, "e5d6")  # exd6 e.p.
    changed = changed_squares(before, after)
    # from e5 (vacated), to d6 (filled), captured pawn d5 (vacated) -> 3 squares.
    assert changed == sorted(["e5", "d6", "d5"])
    assert len(changed) == 3


def test_promotion_two_squares():
    # White pawn on a7 promotes to a queen on a8 (a7a8q): from + to.
    board = chess.Board("8/P6k/8/8/8/8/7K/8 w - - 0 1")
    before, after = _step(board, "a7a8q")
    changed = changed_squares(before, after)
    assert changed == sorted(["a7", "a8"])
    assert len(changed) == 2


def test_diff_is_symmetric():
    board = chess.Board()
    before, after = _step(board, "e2e4")
    assert changed_squares(before, after) == changed_squares(after, before)


def test_no_change_identical_fen():
    fen = chess.Board().fen()
    assert changed_squares(fen, fen) == []


def test_board_map_and_occupied_start_position():
    board = chess.Board()
    fen = board.fen()
    bm = board_map(fen)
    assert len(bm) == 32
    assert bm["e1"] == "K" and bm["e8"] == "k" and bm["a2"] == "P"
    occ = occupied_squares(fen)
    assert occ == set(bm.keys())
    assert "e4" not in occ


def test_board_map_accepts_bare_placement_field():
    full = chess.Board().fen()
    bare = full.split(" ", 1)[0]
    assert board_map(bare) == board_map(full)


@pytest.mark.parametrize("bad", ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP", "x", ""])
def test_malformed_fen_raises(bad):
    with pytest.raises(ValueError):
        board_map(bad)
