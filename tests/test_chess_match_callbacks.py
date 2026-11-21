"""Test the ChessMatch callback hooks (on_move / on_forfeit / on_result).

These callbacks are used by the TUI to drive live board updates and
by future features (time controls, per-move timing) that need to
observe game state without scraping stdout.
"""

import os
import sys
import chess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chess_llm import ChessMatch, RandomPlayer, IllegalMoveForfeit


class _StubPlayer:
    """Returns a fixed sequence of moves, then raises to simulate forfeit.

    When the move list is exhausted, the stub returns whatever the
    first legal move is — but most tests that care about move sequences
    install a max_moves cap so the match terminates before that.
    """
    def __init__(self, moves=None, raise_after=False, name="Stub"):
        self.name = name
        self._moves = list(moves or [])
        self._raise = raise_after
        self.illegal_count = 0

    def get_move(self, board: chess.Board, history_text: str) -> chess.Move:
        if self._raise:
            raise IllegalMoveForfeit(f"{self.name} forfeits")
        if not self._moves:
            return next(iter(board.legal_moves))
        uci = self._moves.pop(0)
        return board.parse_uci(uci)


@pytest.mark.xfail(reason="ChessMatch callbacks not implemented", strict=True)
def test_on_move_fires_after_each_legal_move():
    """on_move(board, san, move) must fire exactly once per legal move."""
    moves_seen = []
    white = _StubPlayer(moves=["e2e4", "g1f3"], name="White")
    black = _StubPlayer(moves=["e7e5", "b8c6"], name="Black")
    match = ChessMatch(
        white, black, delay=0, max_moves=4,
        on_move=lambda b, san, mv: moves_seen.append(san),
    )
    match.play()
    # e4, e5, Nf3, Nc6 — alternating white/black, max 4 plies
    assert moves_seen == ["e4", "e5", "Nf3", "Nc6"]


@pytest.mark.xfail(reason="ChessMatch callbacks not implemented", strict=True)
def test_on_move_receives_correct_board():
    """The board passed to on_move must be the post-move position."""
    captured = []
    def capture(board, san, move):
        captured.append((board.fen(), san, move.uci()))
    white = _StubPlayer(moves=["e2e4"], name="White")
    black = _StubPlayer(moves=["e7e5"], name="Black")
    ChessMatch(white, black, delay=0, max_moves=2, on_move=capture).play()
    # First move: e4 → board has pawn on e4
    fen1, san1, uci1 = captured[0]
    assert san1 == "e4"
    assert uci1 == "e2e4"
    # After 1.e4, it's black's turn; the e4 pawn is on rank 4
    assert " b " in fen1  # black to move after e4
    assert "4P" in fen1.replace("/", "")  # white pawn on rank 4


@pytest.mark.xfail(reason="ChessMatch callbacks not implemented", strict=True)
def test_on_result_fires_on_natural_end():
    """on_result must fire with the final result on game-over."""
    results = []
    white = _StubPlayer(moves=["e2e4"], name="White")
    black = _StubPlayer(moves=["e7e5"], name="Black")
    ChessMatch(white, black, delay=0, on_result=results.append).play()
    # Random walk or stub — game will end via move limit OR checkmate/stalemate.
    # Just assert the callback fired at least once with a valid result.
    assert len(results) == 1
    assert results[0] in ("1-0", "0-1", "1/2-1/2")


@pytest.mark.xfail(reason="ChessMatch callbacks not implemented", strict=True)
def test_on_forfeit_and_on_result_fire_on_forfeit():
    """When a player forfeits, both on_forfeit and on_result must fire."""
    forfeits = []
    results = []
    moves = []
    white = _StubPlayer(raise_after=True, name="White")
    black = _StubPlayer(name="Black")  # black plays forever — but white forfeits first
    # Actually, white moves first; if it forfeits on its move, result is 0-1.
    match = ChessMatch(
        white, black, delay=0,
        on_move=lambda b, san, mv: moves.append(san),
        on_forfeit=lambda p: forfeits.append(p.name),
        on_result=results.append,
    )
    match.play()
    assert forfeits == ["White"]
    assert results == ["0-1"]


@pytest.mark.xfail(reason="ChessMatch callbacks not implemented", strict=True)
def test_callback_exception_does_not_crash_match():
    """A buggy callback must not crash the match."""
    def bad_callback(*args, **kwargs):
        raise RuntimeError("intentional test failure")

    white = _StubPlayer(moves=["e2e4", "d2d4"], name="White")
    black = _StubPlayer(moves=["e7e5", "d7d5"], name="Black")
    # on_move is the most-touched callback — verify it absorbs exceptions
    result = ChessMatch(
        white, black, delay=0,
        on_move=bad_callback,
        on_result=bad_callback,
        on_forfeit=bad_callback,
    ).play()
    assert result in ("1-0", "0-1", "1/2-1/2")
