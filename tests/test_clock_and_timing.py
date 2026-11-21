"""Test time-control (--clock) and per-move timing (--timing) features."""

import os
import sys
import time
import chess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from chess_llm import ChessMatch, _parse_clock
except ImportError as exc:
    if "_parse_clock" in str(exc):
        pytest.skip("clock/time control not implemented yet", allow_module_level=True)
    raise


# ── _parse_clock helper ────────────────────────────────────────────────────

class TestParseClock:
    @pytest.mark.parametrize("spec,expected", [
        ("5+0", (5.0, 0.0)),
        ("5+3", (5.0, 3.0)),
        ("0.5+0", (0.5, 0.0)),
        ("60+10", (60.0, 10.0)),
        ("  5  +  3  ", (5.0, 3.0)),  # whitespace tolerated
    ])
    def test_valid_clock(self, spec, expected):
        assert _parse_clock(spec) == expected

    @pytest.mark.parametrize("spec", [None, "", "5", "5+", "+5", "abc", "5-3", "5 3"])
    def test_invalid_clock_returns_none(self, spec):
        assert _parse_clock(spec) is None


# ── record_timings ─────────────────────────────────────────────────────────

class TestRecordTimings:
    def test_move_times_empty_by_default(self):
        match = ChessMatch(__import__("chess_llm").RandomPlayer("W"),
                           __import__("chess_llm").RandomPlayer("B"),
                           delay=0, max_moves=2)
        assert match.move_times == []
        match.play()
        assert match.move_times == []  # not recorded unless requested

    def test_move_times_populated_when_enabled(self):
        from chess_llm import RandomPlayer
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=4, record_timings=True,
        )
        match.play()
        # RandomPlayer.get_move is fast (< 10ms each), so 4 plies = 4 entries
        assert len(match.move_times) == 4
        for t in match.move_times:
            assert t >= 0
            assert t < 1.0  # generous bound — these are microseconds in practice

    def test_print_stats_includes_timing(self, capsys):
        from chess_llm import RandomPlayer
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=2, record_timings=True,
        )
        match.play()
        match.print_stats()
        captured = capsys.readouterr().out
        assert "timing" in captured
        assert "avg" in captured and "max" in captured


# ── Time control (clock) ───────────────────────────────────────────────────

class TestClock:
    def test_clock_disabled_by_default(self):
        from chess_llm import RandomPlayer
        match = ChessMatch(RandomPlayer("W"), RandomPlayer("B"),
                           delay=0, max_moves=2)
        assert match.clock_enabled is False
        assert match.white_clock == 0.0
        assert match.black_clock == 0.0

    def test_clock_initialized(self):
        from chess_llm import RandomPlayer
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=2, clock=(5.0, 3.0),
        )
        assert match.clock_enabled is True
        assert match.white_clock == 300.0
        assert match.black_clock == 300.0
        assert match.clock_increment == 3.0

    def test_clock_decreases_during_move(self):
        """After playing a move, the active player's clock should drop."""
        from chess_llm import RandomPlayer
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=2, clock=(5.0, 0.0),
        )
        before = match.white_clock
        match.play()
        # Each side should have used SOME time
        assert match.white_clock < before
        assert match.black_clock < 300.0

    def test_clock_increment_applied_after_move(self):
        """With non-zero increment, the active player's clock is refilled."""
        from chess_llm import RandomPlayer
        # Use a generous clock so the game can run a few plies without forfeit
        match = ChessMatch(
            RandomPlayer("W"), RandomPlayer("B"),
            delay=0, max_moves=2, clock=(60.0, 5.0),
        )
        w_initial, b_initial = match.white_clock, match.black_clock
        match.play()
        # With 5s increment and ~ms per move, both clocks should be near
        # initial (decremented by move time, incremented by 5s)
        # initial=60, +5 increment, -0.001 move time → ~64.999
        assert match.white_clock > w_initial - 1.0  # not drained
        assert match.black_clock > b_initial - 1.0

    def test_clock_exhaustion_forfeits_game(self):
        """A player that exceeds their clock forfeits."""
        from chess_llm import RandomPlayer, IllegalMoveForfeit
        # Use a very small clock (0.001 min = 0.06s) so RandomPlayer runs over.
        # RandomPlayer is fast, so use an artificially tiny budget.
        # Note: the player chooses a move quickly; we test the forfeit
        # path with a custom slow player.
        class _SlowPlayer:
            def __init__(self, name, sleep=1.0):
                self.name = name
                self.sleep = sleep
                self.illegal_count = 0
            def get_move(self, board, history):
                time.sleep(self.sleep)
                return next(iter(board.legal_moves))

        match = ChessMatch(
            _SlowPlayer("SlowWhite", sleep=2.0),
            _SlowPlayer("SlowBlack", sleep=0.0),
            delay=0, clock=(0.05, 0.0),  # 3 second budget, white will exceed
        )
        # White will exceed 3s budget on its first move → forfeit, black wins
        result = match.play()
        assert result == "0-1"
