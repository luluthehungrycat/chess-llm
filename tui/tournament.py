"""Tournament TUI dashboard for LLM Chess."""

import time
from typing import Optional

import chess
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Header, Footer, Static, ProgressBar, DataTable, RichLog,
    Label,
)
from textual import work

from elo import EloTracker
from .board import BoardWidget
from .common import TUI_CSS
from .runner import TournamentRunner, _elo_id
from .state import save_state, clear_state


class ELOComputer:
    """In-memory ELO computer — no disk I/O, fast for live updates."""

    def __init__(self, initial_rating: int = 1200):
        self.initial = initial_rating
        self.ratings: dict[str, dict] = {}

    def _get(self, pid: str) -> dict:
        return self.ratings.get(pid, {
            "rating": self.initial, "games": 0, "wins": 0, "losses": 0, "draws": 0,
        })

    def load_existing(self, db_path: str):
        """Load existing ratings from a JSON file (e.g. ratings.json)."""
        import json, os
        if os.path.exists(db_path):
            with open(db_path) as f:
                data = json.load(f)
            self.ratings = data
            return len(data)
        return 0

    def update(self, white_id: str, black_id: str, result: str):
        if white_id == black_id:
            return  # self-play is unrated (matches elo.EloTracker)
        w = self._get(white_id)
        b = self._get(black_id)

        w_r, b_r = w["rating"], b["rating"]
        w_exp = 1.0 / (1.0 + 10.0 ** ((b_r - w_r) / 400.0))

        K = 64 if w["games"] < 10 else 32
        K_b = 64 if b["games"] < 10 else 32

        if result == "1-0":
            w_score, b_score = 1.0, 0.0
            w["wins"] += 1
            b["losses"] += 1
        elif result == "0-1":
            w_score, b_score = 0.0, 1.0
            w["losses"] += 1
            b["wins"] += 1
        else:
            w_score, b_score = 0.5, 0.5
            w["draws"] = w.get("draws", 0) + 1
            b["draws"] = b.get("draws", 0) + 1

        w["rating"] = round(w_r + K * (w_score - w_exp))
        b["rating"] = round(b_r + K_b * (b_score - (1.0 - w_exp)))
        w["games"] += 1
        b["games"] += 1

        self.ratings[white_id] = w
        self.ratings[black_id] = b

    def leaderboard(self) -> list[tuple[str, dict]]:
        return sorted(
            self.ratings.items(),
            key=lambda x: x[1]["rating"],
            reverse=True,
        )


class TournamentApp(App):
    """Textual TUI for tournament dashboard."""

    CSS = TUI_CSS + """
    #dashboard { height: auto; }
    #board-panel { width: 29; height: auto; }
    #worker-log { height: 1fr; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause/Resume"),
        ("s", "save", "Save progress"),
        ("b", "toggle_board", "Toggle board"),
    ]

    def __init__(
        self,
        models: list[str],
        games_per_pair: int,
        delay: float,
        elo_db_path: Optional[str],
        player_kwargs: dict,
        max_workers: int,
        resume_completed: Optional[list[tuple[str, str, str]]] = None,
        resume_elo: Optional[dict] = None,
        openings_mode: str = "standard",
    ):
        super().__init__()
        self.models = models
        self.games_per_pair = games_per_pair
        self.delay = delay
        self.elo_db_path = elo_db_path
        self.player_kwargs = player_kwargs
        self.max_workers = max_workers
        self.openings_mode = openings_mode

        self._resume_elo = resume_elo or {}
        self.elo = ELOComputer()
        self.runner = TournamentRunner(
            models, games_per_pair, delay, max_workers, player_kwargs, self.elo,
            resume_completed=resume_completed, openings_mode=openings_mode,
        )
        self._tournament_started_at = 0.0
        self._paused = False
        self._completion_reported = False
        self._show_board = True
        self._last_board_fen: str | None = None
        self._last_game_info = ""

    # ── Compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="progress-section"):
            yield Label("", id="progress-label")
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        with Horizontal(id="dashboard"):
            with Vertical():
                yield Static("", id="active-games")
                yield DataTable(id="elo-table", cursor_type="row")
                yield Static("", id="matchup-summary")
            with Vertical(id="board-panel"):
                yield BoardWidget(id="board-view")
                yield Static("", id="board-game-label")
        yield RichLog(id="worker-log", max_lines=20, highlight=True, markup=True)
        yield Footer()

    # ── Mount ────────────────────────────────────────────────────────────

    def on_mount(self):
        # A resumed tournament includes its most recently saved ratings.
        if self._resume_elo:
            self.elo.ratings = self._resume_elo
        elif self.elo_db_path:
            loaded = self.elo.load_existing(self.elo_db_path)
            if loaded:
                self._tui_log(f"📂 Loaded {loaded} existing ratings from {self.elo_db_path}")

        self._tournament_started_at = time.time()
        self._initial_completed = len(self.runner.completed)
        self.query_one("#elo-table", DataTable).add_columns("#", "Player", "ELO", "G", "W", "L", "D")
        self._tui_log(f"⚙ Tournament: {len(self.models)} players, "
                      f"{self.runner.total_tasks} tasks, {self.max_workers} workers")
        if self._initial_completed:
            self.notify(f"Resumed with {self._initial_completed} completed games", title="📂 Resume")
        self._start_workers()
        self._poll_timer = self.set_interval(0.2, self._poll)

    def _tui_log(self, msg: str):
        self.query_one("#worker-log", RichLog).write(Text(msg))

    @work(thread=True)
    def _start_workers(self):
        self.runner.start()

    def _poll(self):
        """Drain worker events and refresh the dashboard."""
        self.runner.process_moves()
        finished = self.runner.is_finished()
        for white, black, result, _, fen, _ in self.runner.process_results():
            if result == "error":
                self._tui_log(f"Game failed: {white} vs {black}")
            elif fen:
                self._last_board_fen = fen
                self._last_game_info = f"{white} vs {black} · {result}"

        self._update_progress()
        self._update_active_games()
        self._update_elo_table()
        self._update_matchup_summary()
        self._refresh_board()

        if finished and self.runner.is_complete() and not self._completion_reported:
            self._completion_reported = True
            self._on_complete()

    def _refresh_board(self):
        panel = self.query_one("#board-panel", Vertical)
        panel.display = self._show_board
        if not self._show_board:
            return
        live = self.runner.latest_live_state()
        if live is None:
            self._update_board()
            return
        board, san, white, black, _, _ = live
        self.query_one("#board-view", BoardWidget).update_state(
            board=board, last_move=board.peek() if board.move_stack else None,
        )
        self.query_one("#board-game-label", Static).update(Text(f"{white} vs {black} · {san}"))

    def _update_board(self):
        """Display the last completed position when there is no live game."""
        if not self._show_board or self.runner.latest_live_state() is not None:
            return
        board = chess.Board(self._last_board_fen) if self._last_board_fen else chess.Board()
        self.query_one("#board-view", BoardWidget).update_state(board=board)
        self.query_one("#board-game-label", Static).update(Text(self._last_game_info))

    # ── Widget updates ───────────────────────────────────────────────────

    def _update_progress(self):
        done = len(self.runner.completed)
        total = self.runner.total_tasks
        pct = done * 100 // total if total > 0 else 0
        elapsed = time.time() - self._tournament_started_at

        if done > self._initial_completed and not self.runner.is_finished():
            eta = elapsed / (done - self._initial_completed) * (total - done)
            eta_str = f"{eta:.0f}s" if eta < 120 else f"{eta/60:.1f}m"
        else:
            eta_str = "..."

        elapsed_str = f"{elapsed:.0f}s" if elapsed < 120 else f"{elapsed/60:.1f}m"

        label = self.query_one("#progress-label", Label)
        status = "⚡ Running"
        if self.runner.is_finished():
            status = "🏁 Complete!  Press q to quit." if self.runner.is_complete() else "Games unfinished"
        elif self._paused:
            status = "⏸ Paused"
        label.update(
            f"  {status}  [{done}/{total}] {pct}%  "
            f"⏱ {elapsed_str} elapsed  ·  ~{eta_str} remaining  "
            f"·  {self.max_workers} workers"
        )

        bar = self.query_one("#progress-bar", ProgressBar)
        bar.update(total=total, progress=done)

    def _update_active_games(self):
        active = self.query_one("#active-games", Static)
        items = list(self.runner.active_snapshot().values())
        if not items:
            active.update("  No active games.")
            return

        lines = ["  ▶ Live games:"]
        for wm, bm, started in items[:8]:
            elapsed = time.time() - started
            lines.append(f"    {wm}  vs  {bm}   ···  {elapsed:.0f}s")
        if len(items) > 8:
            lines.append(f"    ... and {len(items) - 8} more")
        active.update("\n".join(lines))

    def _update_elo_table(self):
        table = self.query_one("#elo-table", DataTable)
        table.clear()

        board = self.elo.leaderboard()
        for i, (pid, stats) in enumerate(board[:20], 1):
            table.add_row(
                str(i), pid,
                str(stats["rating"]),
                str(stats["games"]),
                str(stats.get("wins", 0)),
                str(stats.get("losses", 0)),
                str(stats.get("draws", 0)),
            )

    def _update_matchup_summary(self):
        widget = self.query_one("#matchup-summary", Static)
        if not self.runner.completed:
            widget.update("")
            return

        summary: dict[str, dict[str, int]] = {}
        for wm, bm, result in self.runner.completed:
            wid = _elo_id(wm)
            bid = _elo_id(bm)
            for pid in (wid, bid):
                if pid not in summary:
                    summary[pid] = {"W": 0, "D": 0, "L": 0}
            if result == "1-0":
                summary[wid]["W"] += 1
                summary[bid]["L"] += 1
            elif result == "0-1":
                summary[wid]["L"] += 1
                summary[bid]["W"] += 1
            else:
                summary[wid]["D"] += 1
                summary[bid]["D"] += 1

        lines = ["  📊  Results:  W–D–L"]
        board = self.elo.leaderboard()
        for pid, _ in board[:10]:
            if pid in summary:
                s = summary[pid]
                short = pid if len(pid) <= 16 else pid[:13] + "..."
                lines.append(f"    {short:<17} {s['W']}–{s['D']}–{s['L']}")

        widget.update("\n".join(lines))

    def _save_elo(self):
        """Save accumulated ELO ratings to disk.

        Since we loaded existing ratings at startup and accumulated new games
        in-memory, self.elo.ratings already contains the correct merged data
        (old ratings + new games). Just write it out.
        """
        if self.elo_db_path and self.elo.ratings:
            from elo import EloTracker
            tracker = EloTracker(self.elo_db_path)
            # Replace tracker's in-memory dict with our accumulated data
            tracker._ratings = self.elo.ratings
            tracker._save()
            return True
        return False

    def _on_complete(self):
        """Tournament finished — show final state and save ELO."""
        self.query_one("#progress-label", Label).update(
            "  🏁 Tournament complete!  Press q to quit."
        )
        if self._save_elo():
            self.notify(f"ELO saved to {self.elo_db_path}", title="✅ Done")
        clear_state()

    # ── Actions ──────────────────────────────────────────────────────────

    def action_quit(self):
        """Quit: save ELO, stop workers, then exit."""
        self._poll_timer.stop()
        self.runner.stop()
        # Drain any remaining results
        self._poll()
        if not self.runner.is_complete():
            self.action_save()
            self._save_elo()
        self.exit()

    def action_toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self.runner.pause()
        else:
            self.runner.resume()
        self.notify("Paused" if self._paused else "Resumed")

    def action_toggle_board(self):
        self._show_board = not self._show_board
        self._refresh_board()

    def action_save(self):
        """Save tournament progress to disk for later resume."""
        path = save_state(
            models=self.models,
            games_per_pair=self.games_per_pair,
            delay=self.delay,
            max_workers=self.max_workers,
            player_kwargs=self.player_kwargs,
            completed=self.runner.completed,
            elo_ratings=self.elo.ratings,
            elo_db_path=self.elo_db_path,
            started_at=self._tournament_started_at,
        )
        self.notify(f"Saved {len(self.runner.completed)} games to {path}", title="💾 Saved")
