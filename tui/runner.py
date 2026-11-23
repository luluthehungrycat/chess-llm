"""Tournament runner — orchestrates game workers without any Textual deps.

TournamentRunner owns the worker thread pool, the result queue, and the
move queue. It is the bridge between TournamentApp (Textual UI) and
tournament.run_match (game logic). The runner doesn't know about
widgets or rendering — it just pushes events onto queues that the UI
drains.
"""

import queue
import threading
import time
from typing import Optional

import chess


# Canonical ELO key, shared with tournament.py
from elo import player_id as _elo_id
from .state import ScheduledGame, build_schedule, _subtract_completed


class TournamentRunner:
    """Runs tournament games using a thread pool, queues results + moves.

    The UI (TournamentApp) drives the runner:
      - call .start() once after construction
      - periodically drain .results and .moves queues in the UI loop
      - call .stop() to halt workers

    Threading model:
      - One background thread (the Textual @work thread that calls start)
        dispatches tasks to a ThreadPoolExecutor.
      - Worker threads push (wm, bm, result, duration, pgn_fen, move_count)
        onto .results, and (tid, board_copy, san, wm, bm) onto .moves.
      - The UI thread drains both queues in its poll loop.
    """

    def __init__(
        self,
        models: list[str],
        games_per_pair: int,
        delay: float,
        max_workers: int,
        player_kwargs: dict,
        elo_tracker,                    # EloTracker — single source of truth
        resume_completed: Optional[list[tuple[str, str, str]]] = None,
        openings_mode: str = "standard",
        schedule: list[ScheduledGame] | None = None,
    ):
        self.models = models
        self.games_per_pair = games_per_pair
        self.delay = delay
        self.max_workers = max_workers
        self.player_kwargs = player_kwargs
        self.elo_tracker = elo_tracker
        self.openings_mode = openings_mode

        # Resume state
        self._resume_completed = [
            item for item in resume_completed or [] if item[2] != "error"
        ]
        self._completed = list(self._resume_completed)
        self._failures: list[tuple[str, str, str]] = []

        # Compute the task list eagerly so .total_tasks is accurate before start()
        self._task_list = schedule if schedule is not None else _subtract_completed(
            build_schedule(models, games_per_pair, openings_mode), self._resume_completed
        )
        self._completed_task_ids: set[int] = set()
        self._active: dict[int, tuple[str, str, float]] = {}
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._pause_gate = threading.Event()
        self._pause_gate.set()
        self._finished = False
        self._start_time = 0.0
        self._live_sequence = 0
        # tid -> (board_copy, san, wm, bm, fullmove, side, sequence)
        self._live_state: dict[int, tuple] = {}
        # Worker-owned final state, independent of UI queue draining.
        self._final_state: dict[int, tuple[chess.Board, int]] = {}
        # Per-player game durations
        self._game_durations: dict[str, list[float]] = {}

        # Public queues for the UI to drain
        self.results: queue.Queue = queue.Queue()
        self.moves: queue.Queue = queue.Queue()

    # ── Public API ────────────────────────────────────────────────────────

    def start(self):
        """Begin tournament execution in a background thread.

        This method is non-blocking — it returns immediately after
        kicking off the worker pool. The caller is expected to drain
        .results and .moves from the UI thread.
        """
        self._start_time = time.time()
        if not self._task_list:
            self._finished = True
            return
        self._dispatch_loop()

    def stop(self):
        self._stop_flag.set()
        self._pause_gate.set()

    def pause(self):
        self._pause_gate.clear()

    def resume(self):
        self._pause_gate.set()

    def is_finished(self) -> bool:
        return self._finished

    def is_complete(self) -> bool:
        return self._finished and len(self._completed) >= self.total_tasks

    @property
    def total_tasks(self) -> int:
        return len(self._task_list) + len(self._resume_completed)

    @property
    def completed(self) -> list[tuple[str, str, str]]:
        return self._completed

    def remaining_games(self) -> list[ScheduledGame]:
        return [
            game for task_id, game in enumerate(self._task_list)
            if task_id not in self._completed_task_ids
        ]

    def active_snapshot(self) -> dict[int, tuple[str, str, float]]:
        with self._lock:
            return dict(self._active)

    def game_durations(self) -> dict[str, list[float]]:
        return self._game_durations

    def latest_live_state(self) -> Optional[tuple]:
        """Return the most recently updated live board state."""
        with self._lock:
            if not self._live_state:
                return None
            return max(self._live_state.values(), key=lambda state: state[-1])[:-1]

    # ── Internal ─────────────────────────────────────────────────────────

    def _dispatch_loop(self):
        """Submit all tasks to a thread pool, then block until they complete.

        Designed to be run in a Textual @work(thread=True) worker thread.
        """
        import concurrent.futures
        # Resolve run_match once
        import sys
        _mod = sys.modules.get("__main__")
        if _mod is not None and hasattr(_mod, "run_match"):
            _run_match_fn = _mod.run_match
        else:
            from tournament import run_match as _run_match_fn

        def _on_move_factory(task_id, wm, bm):
            def _on_move(board, san, _move):
                board_copy = board.copy()
                with self._lock:
                    self._final_state[task_id] = (board_copy, len(board_copy.move_stack))
                    self._live_sequence += 1
                    side = "White" if board_copy.turn == chess.WHITE else "Black"
                    self._live_state[task_id] = (
                        board_copy, san, wm, bm, board_copy.fullmove_number,
                        side, self._live_sequence,
                    )
                self.moves.put((task_id, board_copy, san, wm, bm))
            return _on_move

        def _run_one(tid, game):
            wm, bm = game.white, game.black
            self._pause_gate.wait()
            if self._stop_flag.is_set():
                return
            start_ts = time.time()
            with self._lock:
                self._active[tid] = (wm, bm, start_ts)

            on_move_cb = _on_move_factory(tid, wm, bm)

            try:
                board = game.starting_board()
                result = _run_match_fn(
                    wm, bm,
                    delay=self.delay, elo_tracker=None,
                    starting_board=board, opening_name=game.opening_name,
                    on_move=on_move_cb,
                    quiet=True,
                    **self.player_kwargs,
                )
                duration = time.time() - start_ts

                # Final state is captured by the worker callback, not UI polling.
                with self._lock:
                    final = self._final_state.get(tid)
                if final is not None:
                    final_board, move_count = final
                    pgn_fen = final_board.fen()
                else:
                    pgn_fen = board.fen() if board else ""
                    move_count = len(board.move_stack) if board else 0

                self.results.put((wm, bm, result, duration, pgn_fen, move_count, tid))
            except Exception as e:
                self.results.put((wm, bm, "error", 0.0, "", 0, tid))
                with open("/tmp/tui_worker.log", "a") as _wf:
                    _wf.write(f"[runner] Task {wm} vs {bm} FAILED: {e}\n")
                    import traceback
                    traceback.print_exc(file=_wf)
            finally:
                with self._lock:
                    self._active.pop(tid, None)
                    self._live_state.pop(tid, None)
                    self._final_state.pop(tid, None)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = []
            for tid, game in enumerate(self._task_list):
                if self._stop_flag.is_set():
                    break
                self._pause_gate.wait()
                if self._stop_flag.is_set():
                    break
                futures.append(executor.submit(_run_one, tid, game))
            for future in concurrent.futures.as_completed(futures):
                if self._stop_flag.is_set():
                    break
                try:
                    future.result()
                except Exception:
                    pass
        self._finished = True

    # ── Result / move processing (called from UI thread) ─────────────────

    def process_results(self):
        """Drain the results queue, update ELO, track durations.

        Returns a list of (white, black, result, duration) tuples for
        games that completed this poll cycle.
        """
        processed = []
        while not self.results.empty():
            try:
                item = self.results.get_nowait()
            except queue.Empty:
                break
            task_id = item[6] if len(item) == 7 else None
            if len(item) >= 6:
                white, black, result, duration, pgn_fen, move_count = item[:6]
            else:
                # Backwards-compat with shorter tuples
                white, black, result = item[:3]
                duration = item[3] if len(item) > 3 else 0.0
                pgn_fen = item[4] if len(item) > 4 else ""
                move_count = item[5] if len(item) > 5 else 0
            if result == "error":
                self._failures.append((white, black, result))
            else:
                self._completed.append((white, black, result))
            if result != "error":
                w_id = _elo_id(white)
                b_id = _elo_id(black)
                self.elo_tracker.update(w_id, b_id, result)
                if task_id is not None:
                    self._completed_task_ids.add(task_id)
                for pid in (w_id, b_id):
                    self._game_durations.setdefault(pid, []).append(duration)
            processed.append((white, black, result, duration, pgn_fen, move_count))
        return processed

    def process_moves(self) -> list[tuple]:
        """Drain the moves queue.

        Returns the full list of moves drained this cycle (for callers
        that want to inspect them). The most recent live state is
        available via .latest_live_state().
        """
        drained = []
        while not self.moves.empty():
            try:
                item = self.moves.get_nowait()
            except queue.Empty:
                break
            drained.append(item)
        return drained
