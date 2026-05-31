# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Unit tests for the move -> PieceAction decomposition (no ROS required).

These exercise the crux logic for every special case the spec calls out:
quiet move, capture, castling (both sides), en passant, promotion, and
capture-promotion.  They use a small inline board_coordinates.yaml so the tests
run without a sourced ROS install.
"""

import os
import tempfile

import chess
from chess_arm_orchestrator.piece_actions import (
    BoardCoordinates,
    CLEAR_CAPTURE,
    CLEAR_EN_PASSANT,
    decompose_move,
    GraveyardAllocator,
    MOVE_ROOK,
    PICK_PLACE,
    PLACE_PROMOTION,
    REMOVE_PROMOTED_PAWN,
)
import pytest

FILES = 'abcdefgh'


def _write_coords(path):
    """Generate a deterministic board_coordinates.yaml mirroring the real one."""
    lines = [
        'units: m',
        'surface_z: 0.0',
        'grasp_z: 0.03',
        'lift_z: 0.11',
        'squares:',
    ]
    sq = 0.057150
    for fi in range(8):
        for ri in range(8):
            name = f'{FILES[fi]}{ri + 1}'
            x = round((fi - 3.5) * sq, 6)
            y = round((ri - 3.5) * sq, 6)
            lines.append(f'  {name}:')
            lines.append(f'    x: {x}')
            lines.append(f'    y: {y}')
    lines.append('graveyard:')
    n = 0
    for rx in (0.285, 0.32):
        for c in range(8):
            n += 1
            lines.append(f'  GY{n}:')
            lines.append(f'    x: {rx}')
            lines.append(f'    y: {round(-0.16 + c * 0.04, 6)}')
    with open(path, 'w') as fh:
        fh.write('\n'.join(lines) + '\n')


@pytest.fixture()
def coords():
    """Provide a BoardCoordinates backed by a temp board_coordinates.yaml."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'board_coordinates.yaml')
        _write_coords(path)
        yield BoardCoordinates(path)


@pytest.fixture()
def alloc(coords):
    """Provide a fresh GraveyardAllocator for the test coords."""
    return GraveyardAllocator(coords)


def _decompose(fen, uci, coords, alloc):
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    return board, decompose_move(board, move, coords, alloc)


# -- coordinate plumbing ----------------------------------------------------

def test_coords_lookup_grasp_height(coords):
    """grasp_point uses grasp_z and the right square xy."""
    pt = coords.grasp_point('e2')
    assert pt.z == pytest.approx(coords.grasp_z)
    # e-file is index 4 -> (4-3.5)*sq; rank 2 -> (1-3.5)*sq.
    assert pt.x == pytest.approx((4 - 3.5) * 0.057150, abs=1e-6)
    assert pt.y == pytest.approx((1 - 3.5) * 0.057150, abs=1e-6)


def test_graveyard_reserves_promotion_source(coords):
    """Last slot is reserved as the promotion source; clears start at GY1."""
    a = GraveyardAllocator(coords)
    slots = coords.graveyard_slots()
    assert a.promotion_source_slot == slots[-1] == 'GY16'
    first = a.next_slot()
    assert first == 'GY1'
    assert a.promotion_source_slot == 'GY16'


# -- quiet move -------------------------------------------------------------

def test_quiet_move(coords, alloc):
    """A quiet move is a single PICK_PLACE."""
    _board, actions = _decompose(chess.STARTING_FEN, 'e2e4', coords, alloc)
    assert len(actions) == 1
    a = actions[0]
    assert a.action_type == PICK_PLACE
    assert (a.from_square, a.to_square) == ('e2', 'e4')
    assert a.piece == 'P'
    assert a.from_xyz.z == pytest.approx(coords.grasp_z)


# -- ordinary capture -------------------------------------------------------

def test_capture_clears_then_moves(coords, alloc):
    """A capture clears the victim then relocates the attacker."""
    fen = 'rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1'
    _board, actions = _decompose(fen, 'd4e5', coords, alloc)
    assert [x.action_type for x in actions] == [CLEAR_CAPTURE, PICK_PLACE]
    clear, move = actions
    assert clear.from_square == 'e5'
    assert clear.to_square == 'GY1'
    assert clear.piece == 'p'  # black pawn
    assert (move.from_square, move.to_square) == ('d4', 'e5')
    assert move.piece == 'P'


# -- castling ---------------------------------------------------------------

def test_castle_kingside(coords, alloc):
    """Kingside castle = king e1->g1, then rook h1->f1."""
    fen = 'rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1'
    _board, actions = _decompose(fen, 'e1g1', coords, alloc)
    assert [x.action_type for x in actions] == [PICK_PLACE, MOVE_ROOK]
    king, rook = actions
    assert (king.from_square, king.to_square) == ('e1', 'g1')
    assert king.piece == 'K'
    assert (rook.from_square, rook.to_square) == ('h1', 'f1')
    assert rook.piece == 'R'


def test_castle_queenside(coords, alloc):
    """Queenside castle = king e1->c1, then rook a1->d1."""
    fen = 'r3kbnr/pppqpppp/2n5/3p1b2/3P1B2/2N5/PPPQPPPP/R3KBNR w KQkq - 0 1'
    _board, actions = _decompose(fen, 'e1c1', coords, alloc)
    assert [x.action_type for x in actions] == [PICK_PLACE, MOVE_ROOK]
    king, rook = actions
    assert (king.from_square, king.to_square) == ('e1', 'c1')
    assert (rook.from_square, rook.to_square) == ('a1', 'd1')
    assert rook.piece == 'R'


# -- en passant -------------------------------------------------------------

def test_en_passant_white(coords, alloc):
    """White e.p.: clear the captured pawn behind the destination, then move."""
    fen = 'rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 1'
    _board, actions = _decompose(fen, 'e5d6', coords, alloc)
    assert [x.action_type for x in actions] == [CLEAR_EN_PASSANT, PICK_PLACE]
    clear, move = actions
    assert clear.from_square == 'd5'
    assert clear.to_square == 'GY1'
    assert clear.piece == 'p'
    assert (move.from_square, move.to_square) == ('e5', 'd6')
    assert move.piece == 'P'


def test_en_passant_black(coords, alloc):
    """Black e.p.: captured white pawn sits behind the destination."""
    fen = 'rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
    _board, actions = _decompose(fen, 'd4e3', coords, alloc)
    assert [x.action_type for x in actions] == [CLEAR_EN_PASSANT, PICK_PLACE]
    clear, move = actions
    assert clear.from_square == 'e4'
    assert clear.piece == 'P'  # white pawn
    assert (move.from_square, move.to_square) == ('d4', 'e3')


# -- promotion --------------------------------------------------------------

def test_quiet_promotion(coords, alloc):
    """Quiet promotion: remove pawn, then place the spare queen on dest."""
    # Black king on a8 so e8 is genuinely empty and reachable.
    fen = 'k7/4P3/8/8/8/8/8/4K3 w - - 0 1'
    _board, actions = _decompose(fen, 'e7e8q', coords, alloc)
    assert [x.action_type for x in actions] == [
        REMOVE_PROMOTED_PAWN, PLACE_PROMOTION]
    remove, place = actions
    assert remove.from_square == 'e7'
    assert remove.to_square == 'GY1'   # pawn removed to a fresh slot
    assert remove.piece == 'P'
    assert place.from_square == 'GY16'  # spare queen from reserved source
    assert place.to_square == 'e8'
    assert place.piece == 'Q'


def test_capture_promotion(coords, alloc):
    """Capture-promotion: clear victim, remove pawn, place spare queen."""
    fen = '3rk3/4P3/8/8/8/8/8/4K3 w - - 0 1'
    _board, actions = _decompose(fen, 'e7d8q', coords, alloc)
    assert [x.action_type for x in actions] == [
        CLEAR_CAPTURE, REMOVE_PROMOTED_PAWN, PLACE_PROMOTION]
    clear, remove, place = actions
    assert clear.from_square == 'd8'
    assert clear.to_square == 'GY1'
    assert clear.piece == 'r'
    assert remove.from_square == 'e7'
    assert remove.to_square == 'GY2'
    assert place.from_square == 'GY16'
    assert place.to_square == 'd8'
    assert place.piece == 'Q'


def test_underpromotion_piece_label(coords, alloc):
    """Underpromotion carries the promoted piece letter (e.g. N)."""
    fen = 'k7/4P3/8/8/8/8/8/4K3 w - - 0 1'
    _board, actions = _decompose(fen, 'e7e8n', coords, alloc)
    place = actions[-1]
    assert place.action_type == PLACE_PROMOTION
    assert place.piece == 'N'


# -- guards -----------------------------------------------------------------

def test_illegal_move_raises(coords, alloc):
    """Decomposing an illegal move raises ValueError."""
    board = chess.Board()
    with pytest.raises(ValueError):
        decompose_move(board, chess.Move.from_uci('e2e5'), coords, alloc)


def test_graveyard_exhaustion(coords):
    """Allocating more clear slots than available raises RuntimeError."""
    a = GraveyardAllocator(coords)
    # 15 clear slots available (16 total, 1 reserved for promotion).
    for _ in range(15):
        a.next_slot()
    with pytest.raises(RuntimeError):
        a.next_slot()


# -- a short full game stays consistent ------------------------------------

def test_full_short_game_decomposes(coords):
    """Decompose every ply of a short game with capture + castling."""
    alloc = GraveyardAllocator(coords)
    board = chess.Board()
    line = ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'g8f6',
            'e1g1', 'f8c5']
    total = 0
    for uci in line:
        move = chess.Move.from_uci(uci)
        actions = decompose_move(board, move, coords, alloc)
        assert actions  # every move yields at least one action
        total += len(actions)
        board.push(move)
    assert total >= len(line)  # castling expands to 2
