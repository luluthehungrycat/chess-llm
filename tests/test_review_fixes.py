import os
import time
from unittest.mock import MagicMock, patch

import chess

from chess_llm import ChessMatch, RandomPlayer
from tui.runner import TournamentRunner
from tui.state import compute_remaining_tasks
from elo import EloTracker


def test_live_board_is_not_overwritten_by_completed_position():
    """The periodic fallback update must preserve the live move board."""
    import pytest
    pytest.importorskip("textual")
    from tui.tournament import TournamentApp

    app = TournamentApp.__new__(TournamentApp)
    app._show_board = True
    app._last_board_fen = chess.Board().fen()
    app._last_game_info = "  Last completed game"
    app.runner = MagicMock()
    app.runner.latest_live_state.return_value = (
        chess.Board(), "e4", "white", "black", 1, "White"
    )
    board_widget = MagicMock()
    label = MagicMock()
    app.query_one = MagicMock(side_effect=[board_widget, label])

    app._update_board()

    board_widget.update_state.assert_not_called()
    label.update.assert_not_called()


def test_board_widget_dimensions_fit_rendered_content():
    import pytest
    pytest.importorskip("textual")
    from tui.board import BoardWidget

    widget = BoardWidget()
    assert widget.render_line(9).cell_length <= 29
    assert widget.render_line(10).cell_length == 29


def test_print_stats_replays_capture_positions(capsys):
    match = ChessMatch(RandomPlayer("W"), RandomPlayer("B"), delay=0)
    for uci in ("e2e4", "d7d5", "e4d5", "g8f6"):
        match.board.push_uci(uci)
    match.print_stats()
    assert "Captures: 1" in capsys.readouterr().out


def test_failed_resume_tasks_are_retried():
    assert compute_remaining_tasks(["a", "b"], 1, [("a", "b", "error")]) == [
        ("a", "b"), ("b", "a")
    ]


def test_live_state_uses_update_sequence(tmp_path):
    tracker = EloTracker(":memory:")
    runner = TournamentRunner(["a", "b"], 1, 0, 1, {}, tracker)
    first = chess.Board()
    second = chess.Board()
    with runner._lock:
        runner._live_sequence = 2
        runner._live_state[1] = (first, "e4", "a", "b", 1, "White", 1)
        runner._live_state[2] = (second, "d5", "b", "a", 1, "Black", 2)
    assert runner.latest_live_state()[1] == "d5"


def test_error_results_are_not_completed(tmp_path):
    runner = TournamentRunner(["a", "b"], 1, 0, 1, {}, EloTracker(":memory:"))
    runner.results.put(("a", "b", "error", 0, "", 0))
    runner.process_results()
    assert runner.completed == []
    assert runner._failures == [("a", "b", "error")]
