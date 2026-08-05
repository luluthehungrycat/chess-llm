"""Test TournamentRunner and elo_view helpers in isolation.

TournamentRunner has no Textual dependency — it just runs workers and
fills queues. The view helpers are pure functions. These tests
exercise both without spinning up the TUI.
"""

import os
import sys
import tempfile
import queue
import time
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tui.runner import TournamentRunner, _elo_id
from tui.elo_view import render_leaderboard_rows, render_matchup_summary
from elo import EloTracker


@pytest.fixture
def fresh_tracker():
    """A fresh EloTracker with no on-disk state, isolated per test."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # ensure _load sees a missing file
    t = EloTracker(path)
    t._ratings = {}  # in case a prior test in another run wrote here
    return t


# ── _elo_id helper ───────────────────────────────────────────────────────

class TestEloId:
    @pytest.mark.parametrize("spec,expected", [
        ("random", "random"),
        ("human", "human-Human"),
        ("human:Alice", "human-Alice"),
        ("stockfish", "stockfish-20"),
        ("stockfish:0", "stockfish-0"),
        ("stockfish-15", "stockfish-15"),
        ("@qwen3-local", "@qwen3-local"),  # passthrough
        ("bigpickle/big-pickle", "bigpickle/big-pickle"),
    ])
    def test_id_extraction(self, spec, expected):
        assert _elo_id(spec) == expected


# ── TournamentRunner: minimal end-to-end ─────────────────────────────────

class TestTournamentRunner:
    def test_empty_tournament_finishes_immediately(self, fresh_tracker):
        runner = TournamentRunner(
            models=[], games_per_pair=1, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=fresh_tracker,
        )
        runner.start()
        # No tasks → finishes synchronously
        assert runner.is_finished()
        assert runner.total_tasks == 0

    def test_active_snapshot_empty_when_idle(self, fresh_tracker):
        runner = TournamentRunner(
            models=["a", "b"], games_per_pair=1, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=fresh_tracker,
        )
        # Don't start — no active games
        assert runner.active_snapshot() == {}

    def test_process_moves_handles_empty_queue(self, fresh_tracker):
        runner = TournamentRunner(
            models=["a", "b"], games_per_pair=1, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=fresh_tracker,
        )
        drained = runner.process_moves()
        assert drained == []
        assert runner.latest_live_state() is None

    def test_process_results_updates_elo(self, fresh_tracker):
        """Manually push to results queue and confirm ELO updates."""
        tracker = fresh_tracker
        # Pre-seed both players as established (>=10 games) so K=32 applies
        for pid in ("a", "b"):
            tracker._ratings[pid] = {
                "rating": 1500, "games": 10,
                "wins": 5, "losses": 5, "draws": 0,
            }
        runner = TournamentRunner(
            models=["a", "b"], games_per_pair=1, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=tracker,
        )
        # Inject a result directly
        runner.results.put(("a", "b", "1-0", 1.0, "", 10))
        processed = runner.process_results()
        assert len(processed) == 1
        # ELO should have been updated: a wins against equal (K=32, expected=0.5)
        # delta = 32 * (1.0 - 0.5) = +16
        assert tracker.get_rating("a") == 1516
        assert tracker.get_rating("b") == 1484
        # Game durations should be tracked
        durs = runner.game_durations()
        assert "a" in durs and "b" in durs
        assert durs["a"] == [1.0] and durs["b"] == [1.0]

    def test_error_result_does_not_update_elo(self, fresh_tracker):
        """An 'error' result must not change ratings but must still be recorded."""
        runner = TournamentRunner(
            models=["x", "y"], games_per_pair=1, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=fresh_tracker,
        )
        runner.results.put(("x", "y", "error", 0.0, "", 0))
        runner.process_results()
        # x, y never had an ELO update (they're brand new — no rating change)
        assert fresh_tracker.get_rating("x") == 1200
        assert fresh_tracker.get_rating("y") == 1200
        # Failed games remain unfinished so resume retries them.
        assert len(runner.completed) == 0
        assert runner._failures == [("x", "y", "error")]

    def test_total_tasks_includes_resume(self, fresh_tracker):
        runner = TournamentRunner(
            models=["a", "b"], games_per_pair=2, delay=0,
            max_workers=1, player_kwargs={}, elo_tracker=fresh_tracker,
            resume_completed=[("a", "b", "1-0")],
        )
        # 2 games per pair * 2 ordered pairs (a→b, b→a) = 4 total
        # - 1 already done = 3 remaining
        assert runner.total_tasks == 4
        assert len(runner._task_list) == 3


# ── elo_view helpers ─────────────────────────────────────────────────────

class TestEloView:
    def test_render_leaderboard_empty(self, fresh_tracker):
        assert render_leaderboard_rows(fresh_tracker) == []

    def test_render_leaderboard_sorted(self, fresh_tracker):
        fresh_tracker._ratings["a"] = {"rating": 1200, "games": 1, "wins": 0, "losses": 0, "draws": 0}
        fresh_tracker._ratings["b"] = {"rating": 1500, "games": 1, "wins": 1, "losses": 0, "draws": 0}
        fresh_tracker._ratings["c"] = {"rating": 1300, "games": 1, "wins": 0, "losses": 1, "draws": 0}
        rows = render_leaderboard_rows(fresh_tracker)
        # Sorted descending by rating: b (1500), c (1300), a (1200)
        assert [r[1] for r in rows] == ["b", "c", "a"]
        # All rows have 7 columns
        for row in rows:
            assert len(row) == 7

    def test_matchup_summary_empty(self, fresh_tracker):
        assert render_matchup_summary([], fresh_tracker, {}) == ""

    def test_matchup_summary_counts_wdl(self, fresh_tracker):
        completed = [
            ("alpha", "beta", "1-0"),   # alpha wins
            ("alpha", "beta", "0-1"),   # beta wins
            ("alpha", "gamma", "1/2-1/2"),  # draw
        ]
        text = render_matchup_summary(completed, fresh_tracker, {}, top_n=10)
        # Matchup summary only shows players that have an ELO rating entry.
        # The view's behaviour is to iterate the leaderboard; in this test
        # none of the players have a rating, so the W-D-L lines are absent.
        # The header should still be present.
        assert "Results" in text
        # For players WITH a rating, the line should appear:
        fresh_tracker._ratings["alpha"] = {"rating": 1500, "games": 3,
                                           "wins": 1, "losses": 1, "draws": 1}
        text2 = render_matchup_summary(completed, fresh_tracker, {}, top_n=10)
        assert "alpha" in text2
        assert "1–1–1" in text2  # 1W, 1L, 1D

    def test_matchup_summary_includes_timing(self, fresh_tracker):
        completed = [("a", "b", "1-0")]
        fresh_tracker._ratings["a"] = {"rating": 1500, "games": 1, "wins": 1, "losses": 0, "draws": 0}
        fresh_tracker._ratings["b"] = {"rating": 1500, "games": 1, "wins": 0, "losses": 1, "draws": 0}
        durations = {"a": [2.0, 3.0, 1.0]}
        text = render_matchup_summary(completed, fresh_tracker, durations, top_n=10)
        assert "2s/game" in text  # avg = 2.0s, format "~2s/game"
