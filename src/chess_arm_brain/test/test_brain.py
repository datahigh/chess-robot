"""Pure-library unit tests for chess_arm_brain (NO ROS).

Run with::

    python3 -m pytest src/chess_arm_brain/test/test_brain.py

The tests play a short, *constructed* line that genuinely reaches:

* a normal quiet move,
* a capture,
* king-side castling,
* an en-passant capture,
* a promotion (and a capture-promotion),

and assert the decompose() action-type sequence and from/to squares for each.
resolve_human_move() is checked against changed-square sets for normal /
capture / castle / en-passant.  The Stockfish test is skipped when the binary
is missing.
"""

import os
import shutil

import chess
import pytest
import yaml

from chess_arm_brain.brain import (
    ACTION_CLEAR_CAPTURE,
    ACTION_CLEAR_EN_PASSANT,
    ACTION_MOVE_ROOK,
    ACTION_PICK_PLACE,
    ACTION_PLACE_PROMOTION,
    ACTION_REMOVE_PROMOTED_PAWN,
    BoardCoordinates,
    ChessBrain,
    GraveyardAllocator,
    PROMOTION_QUEEN_SOURCE,
    StockfishEngine,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers.
# ---------------------------------------------------------------------------
def _write_coords_yaml(tmp_path):
    """Build a minimal but valid board_coordinates.yaml in tmp_path."""
    squares = {}
    files = "abcdefgh"
    # board centre = origin, 0.057150 m squares (matches real generator pitch)
    pitch = 0.057150
    origin = -0.200025
    for fi, f in enumerate(files):
        for r in range(8):
            squares[f"{f}{r + 1}"] = {
                "x": round(origin + fi * pitch, 6),
                "y": round(origin + r * pitch, 6),
            }
    graveyard = {}
    for i in range(1, 17):
        col = 0 if i <= 8 else 1
        row = (i - 1) % 8
        graveyard[f"GY{i}"] = {"x": 0.285 + col * 0.035, "y": -0.16 + row * 0.04}
    data = {
        "units": "m",
        "surface_z": 0.0,
        "grasp_z": 0.030,
        "lift_z": 0.110,
        "squares": squares,
        "graveyard": graveyard,
    }
    path = os.path.join(str(tmp_path), "board_coordinates.yaml")
    with open(path, "w") as fh:
        yaml.safe_dump(data, fh)
    return path


@pytest.fixture
def coords(tmp_path):
    return BoardCoordinates(_write_coords_yaml(tmp_path))


@pytest.fixture
def brain(coords):
    return ChessBrain(coordinates=coords, engine=StockfishEngine())


def _types(actions):
    return [a["action_type"] for a in actions]


def _ft(actions):
    return [(a["from_square"], a["to_square"]) for a in actions]


def _push_uci(b: ChessBrain, uci: str):
    """Decompose-before-push helper returning the decomposition."""
    move = chess.Move.from_uci(uci)
    actions = b.decompose(move)
    b.push(move)
    return move, actions


# ---------------------------------------------------------------------------
# Coordinates helper.
# ---------------------------------------------------------------------------
def test_coordinates_lookup(coords):
    assert coords.grasp_z == pytest.approx(0.030)
    assert coords.lift_z == pytest.approx(0.110)
    assert coords.surface_z == pytest.approx(0.0)
    assert coords.has("e4")
    assert coords.has("GY1")
    assert not coords.has("z9")
    x, y = coords.xy("a1")
    assert (x, y) == pytest.approx((-0.200025, -0.200025))
    x, y, z = coords.xyz("e4")
    assert z == pytest.approx(0.030)
    x, y, z = coords.xyz("e4", coords.lift_z)
    assert z == pytest.approx(0.110)
    assert len(coords.graveyard_slots) == 16
    assert coords.graveyard_slots[0] == "GY1"
    assert coords.graveyard_slots[-1] == "GY16"


def test_graveyard_allocator_reserves_promotion_source(coords):
    alloc = GraveyardAllocator(coords.graveyard_slots)
    handed = [alloc.next_slot() for _ in range(15)]
    # The reserved promotion-queen source must never be handed out as a clear.
    assert PROMOTION_QUEEN_SOURCE not in handed
    assert handed[0] == "GY1"
    with pytest.raises(RuntimeError):
        alloc.next_slot()


# ---------------------------------------------------------------------------
# resolve_human_move() from changed-square sets.
# ---------------------------------------------------------------------------
def test_resolve_normal_move(brain):
    # 1. e4 from the starting position.
    move = brain.resolve_human_move(["e2", "e4"])
    assert move is not None
    assert move.uci() == "e2e4"


def test_resolve_is_order_independent_and_case_insensitive(brain):
    move = brain.resolve_human_move(["E4", "e2"])
    assert move is not None and move.uci() == "e2e4"


def test_resolve_capture(brain):
    # Reach a position where exd5 is legal: 1.e4 d5 -> white to move.
    _push_uci(brain, "e2e4")
    _push_uci(brain, "d7d5")
    # capture exd5: touched set is {e4, d5}.
    move = brain.resolve_human_move(["e4", "d5"])
    assert move is not None and move.uci() == "e4d5"
    # also resolvable from the source-only occupancy flip {e4}.
    move2 = brain.resolve_human_move(["e4"])
    assert move2 is not None and move2.uci() == "e4d5"


def test_resolve_castle(brain):
    # Build a position where white can castle king-side.
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]:
        _push_uci(brain, uci)
    # White king-side castle: king e1->g1, rook h1->f1 -> 4 squares.
    move = brain.resolve_human_move(["e1", "g1", "h1", "f1"])
    assert move is not None and move.uci() == "e1g1"


def test_resolve_en_passant(brain):
    # Construct an en-passant: white pawn to e5, black plays d7-d5, exd6 e.p.
    for uci in ["e2e4", "a7a6", "e4e5", "d7d5"]:
        _push_uci(brain, uci)
    # en passant exd6: touched {e5, d6, d5(captured pawn)}.
    move = brain.resolve_human_move(["e5", "d6", "d5"])
    assert move is not None and move.uci() == "e5d6"
    assert brain.board.is_en_passant(move)


def test_resolve_returns_none_when_illegal(brain):
    assert brain.resolve_human_move(["e2", "e5"]) is None  # no such legal move
    assert brain.resolve_human_move(["a3"]) is None


# ---------------------------------------------------------------------------
# decompose(): the crux.  Action TYPE sequence + from/to squares.
# ---------------------------------------------------------------------------
def test_decompose_normal_quiet(brain):
    move, actions = _push_uci(brain, "e2e4")
    assert _types(actions) == [ACTION_PICK_PLACE]
    assert _ft(actions) == [("e2", "e4")]
    assert actions[0]["piece"] == ""


def test_decompose_capture(brain):
    _push_uci(brain, "e2e4")
    _push_uci(brain, "d7d5")
    move = chess.Move.from_uci("e4d5")
    actions = brain.decompose(move)
    # capture -> clear the captured piece first, then move the attacker.
    assert _types(actions) == [ACTION_CLEAR_CAPTURE, ACTION_PICK_PLACE]
    clear, pick = actions
    assert clear["from_square"] == "d5"  # captured piece is on the destination
    assert clear["to_square"] == "GY1"  # first free graveyard slot
    assert (pick["from_square"], pick["to_square"]) == ("e4", "d5")
    brain.push(move)


def test_decompose_kingside_castle(brain):
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"]:
        _push_uci(brain, uci)
    move = chess.Move.from_uci("e1g1")
    actions = brain.decompose(move)
    # castle -> king first, then rook.
    assert _types(actions) == [ACTION_PICK_PLACE, ACTION_MOVE_ROOK]
    king, rook = actions
    assert (king["from_square"], king["to_square"]) == ("e1", "g1")
    assert (rook["from_square"], rook["to_square"]) == ("h1", "f1")
    brain.push(move)


def test_decompose_queenside_castle():
    # Position with white queen-side castling available.
    fen = "r3kbnr/pppqpppp/2np4/8/3P4/2N1B3/PPPQPPPP/R3KBNR w KQkq - 0 1"
    b = ChessBrain(board=chess.Board(fen))
    # graveyard slots empty here is fine; castle doesn't allocate.
    move = chess.Move.from_uci("e1c1")
    assert move in b.board.legal_moves
    actions = b.decompose(move)
    assert _types(actions) == [ACTION_PICK_PLACE, ACTION_MOVE_ROOK]
    king, rook = actions
    assert (king["from_square"], king["to_square"]) == ("e1", "c1")
    # queen-side: rook a1 -> d1.
    assert (rook["from_square"], rook["to_square"]) == ("a1", "d1")


def test_decompose_en_passant(brain):
    for uci in ["e2e4", "a7a6", "e4e5", "d7d5"]:
        _push_uci(brain, uci)
    move = chess.Move.from_uci("e5d6")
    assert brain.board.is_en_passant(move)
    actions = brain.decompose(move)
    # en passant -> clear the captured pawn (behind dest) first, then move.
    assert _types(actions) == [ACTION_CLEAR_EN_PASSANT, ACTION_PICK_PLACE]
    clear, pick = actions
    # captured pawn sits on d5 (dest file d, mover's start rank 5).
    assert clear["from_square"] == "d5"
    assert clear["to_square"] == "GY1"
    assert (pick["from_square"], pick["to_square"]) == ("e5", "d6")
    brain.push(move)


def test_decompose_promotion(coords):
    # White pawn on e7, e8 empty (black king on h8): e7e8q is a quiet promotion.
    fen = "7k/4P3/8/8/8/8/8/4K3 w - - 0 1"
    b = ChessBrain(coordinates=coords, board=chess.Board(fen))
    move = chess.Move.from_uci("e7e8q")
    assert move in b.board.legal_moves
    actions = b.decompose(move)
    # promotion -> remove the pawn, then place the promoted piece from spare.
    assert _types(actions) == [ACTION_REMOVE_PROMOTED_PAWN, ACTION_PLACE_PROMOTION]
    remove, place = actions
    assert remove["from_square"] == "e7"
    assert remove["to_square"] == "GY1"
    assert place["from_square"] == PROMOTION_QUEEN_SOURCE  # spare queen source
    assert place["to_square"] == "e8"
    assert place["piece"] == "Q"
    b.push(move)


def test_decompose_capture_promotion(coords):
    # White pawn e7 captures a rook on d8 and promotes: e7xd8=Q.
    fen = "3r2k1/4P3/8/8/8/8/8/4K3 w - - 0 1"
    b = ChessBrain(coordinates=coords, board=chess.Board(fen))
    move = chess.Move.from_uci("e7d8q")
    assert move in b.board.legal_moves
    actions = b.decompose(move)
    # capture-promotion -> CLEAR_CAPTURE, then REMOVE_PROMOTED_PAWN, PLACE_PROMOTION.
    assert _types(actions) == [
        ACTION_CLEAR_CAPTURE,
        ACTION_REMOVE_PROMOTED_PAWN,
        ACTION_PLACE_PROMOTION,
    ]
    clear, remove, place = actions
    assert (clear["from_square"], clear["to_square"]) == ("d8", "GY1")
    assert (remove["from_square"], remove["to_square"]) == ("e7", "GY2")
    assert place["from_square"] == PROMOTION_QUEEN_SOURCE
    assert place["to_square"] == "d8"
    assert place["piece"] == "Q"
    b.push(move)


# ---------------------------------------------------------------------------
# A single scripted game exercising every special case in sequence.
# ---------------------------------------------------------------------------
def test_full_scripted_game_exercises_all_cases(coords):
    """One continuous LEGAL game exercising normal, capture, en passant and
    castling decompositions (promotion + capture-promotion are covered by the
    dedicated FEN-based tests above, which is more robust than forcing a
    promotion at the end of a long hand-played line).

    Verified line (white = the arm under test for the special moves):
      1. e4 d5  2. exd5 (CAPTURE) Nf6  3. c4 e5  4. dxe6 e.p. (EN PASSANT) fxe6
      5. Nf3 Nc6  6. Be2 Be7  7. O-O (CASTLE)
    Each special move is decomposed *before* being pushed and checked.
    """
    b = ChessBrain(coordinates=coords, board=chess.Board())

    def step(uci, expect_types=None, expect_ft=None):
        move = chess.Move.from_uci(uci)
        assert move in b.board.legal_moves, f"{uci} illegal in {b.board.fen()}"
        actions = b.decompose(move)
        if expect_types is not None:
            assert _types(actions) == expect_types, (uci, _types(actions))
        if expect_ft is not None:
            assert _ft(actions) == expect_ft, (uci, _ft(actions))
        b.push(move)
        return actions

    # --- a NORMAL move ---
    step("e2e4", expect_types=[ACTION_PICK_PLACE], expect_ft=[("e2", "e4")])
    step("d7d5")

    # --- a CAPTURE: exd5 -> clear the captured pawn on d5, then move e4->d5 ---
    cap = step("e4d5", expect_types=[ACTION_CLEAR_CAPTURE, ACTION_PICK_PLACE])
    assert (cap[0]["from_square"], cap[0]["to_square"]) == ("d5", "GY1")
    assert (cap[1]["from_square"], cap[1]["to_square"]) == ("e4", "d5")

    step("g8f6")
    step("c2c4")
    step("e7e5")  # black 2-square advance, landing beside the white d5 pawn

    # --- EN PASSANT: dxe6 e.p. -> clear captured pawn on e5, then move d5->e6 ---
    ep = step("d5e6", expect_types=[ACTION_CLEAR_EN_PASSANT, ACTION_PICK_PLACE])
    assert (ep[0]["from_square"], ep[0]["to_square"]) == ("e5", "GY2")  # captured pawn
    assert (ep[1]["from_square"], ep[1]["to_square"]) == ("d5", "e6")

    step("f7e6")
    step("g1f3")
    step("b8c6")
    step("f1e2")  # clears f1 so white can castle king-side
    step("f8e7")

    # --- CASTLING (king-side): king first, then rook ---
    step(
        "e1g1",
        expect_types=[ACTION_PICK_PLACE, ACTION_MOVE_ROOK],
        expect_ft=[("e1", "g1"), ("h1", "f1")],
    )

    # Graveyard slots were handed out in order: capture -> GY1, en passant -> GY2;
    # the reserved promotion-queen source GY16 was never allocated.
    assert PROMOTION_QUEEN_SOURCE == "GY16"
    assert not b.is_game_over()


# ---------------------------------------------------------------------------
# with_coordinates(): xyz enrichment.
# ---------------------------------------------------------------------------
def test_with_coordinates_enriches_xyz(brain):
    move = chess.Move.from_uci("e2e4")
    actions = brain.decompose(move)
    enriched = brain.with_coordinates(actions)
    a = enriched[0]
    assert "from_xyz" in a and "to_xyz" in a
    assert len(a["from_xyz"]) == 3
    # default z is grasp height.
    assert a["from_xyz"][2] == pytest.approx(brain.coords.grasp_z)
    # e2 / e4 x-coords must match the coords helper.
    assert a["from_xyz"][0] == pytest.approx(brain.coords.xy("e2")[0])
    assert a["to_xyz"][1] == pytest.approx(brain.coords.xy("e4")[1])


# ---------------------------------------------------------------------------
# Engine test (skipped if Stockfish missing).
# ---------------------------------------------------------------------------
def test_engine_best_move_if_available():
    if shutil.which("stockfish") is None:
        pytest.skip("stockfish binary not installed")
    pytest.importorskip("chess.engine")
    eng = StockfishEngine(skill_level=0, movetime_ms=100)
    b = ChessBrain(engine=eng, board=chess.Board())
    assert not eng.is_open  # lazily opened
    move = b.engine_move()
    assert move in b.board.legal_moves
    assert eng.is_open
    eng.close()
    assert not eng.is_open
