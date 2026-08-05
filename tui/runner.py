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


def _elo_id(spec: str) -> str:
    """Extract a stable ELO key from a player spec without creating a player.

    Mirrors tournament._elo_id_from_spec and chess_llm._elo_id.
    """
    spec = spec.strip()
    if spec.lower() == "random":
        return "random"
    if spec.lower() == "human":
        return "human-Human"
    if spec.startswith("human:"):
        name = spec.split(":", 1)[1].strip()
        return f"human-{name}"
    if spec.lower() == "stockfish":
        return "stockfish-20"
    if spec.lower().startswith("stockfish-") or spec.lower().startswith("stockfish:"):
        suffix = spec[len("stockfish"):].lstrip("-:").strip()
        if suffix.isdigit():
            return f"stockfish-{int(suffix)}"
    return spec


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
    ):
        from .state import compute_remaining_tasks
        self.models = models
        self.games_per_pair = games_per_pair
        self.delay = delay
        self.max_workers = max_workers
        self.player_kwargs = player_kwargs
        self.elo_tracker = elo_tracker
        self.openings_mode = openings_mode

        # Resume state
        self._resume_completed = resume_completed or []
        self._completed: list[tuple[str, str, str]] = [
            item for item in self._resume_completed if item[2] != "error"
        ]
        self._failures: list[tuple[str, str, str]] = []

        # Compute the task list eagerly so .total_tasks is accurate before start()
        self._task_list: list[tuple[str, str]] = compute_remaining_tasks(
            models, games_per_pair, self._resume_completed
        )
        self._active: dict[int, tuple[str, str, float]] = {}
        self._task_id = 0
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
        # Lazily import to avoid pulling in tournament.py at module load time
        from openings import OPENINGS
        import chess as _chess

        openings_list = OPENINGS if self.openings_mode == "unbalanced" else None
        _opening_idx = [0]
        _opening_lock = threading.Lock()

        def _get_opening():
            if openings_list is None:
                return None, ""
            with _opening_lock:
                idx = _opening_idx[0]
                _opening_idx[0] += 1
            name, moves, _adv = openings_list[idx % len(openings_list)]
            board = _chess.Board()
            for uci in moves:
                board.push_uci(uci)
            return board, name

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
                self.moves.put((task_id, board_copy, san, wm, bm))
            return _on_move

        def _run_one(wm, bm):
            start_ts = time.time()
            with self._lock:
                tid = self._task_id
                self._task_id += 1
                self._active[tid] = (wm, bm, start_ts)

            board, oname = _get_opening()
            on_move_cb = _on_move_factory(tid, wm, bm)

            try:
                result = _run_match_fn(
                    wm, bm,
                    delay=self.delay, elo_tracker=None,
                    starting_board=board, opening_name=oname,
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

                self.results.put((wm, bm, result, duration, pgn_fen, move_count))
            except Exception as e:
                self.results.put((wm, bm, "error", 0.0, "", 0))
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
            for wm, bm in self._task_list:
                if self._stop_flag.is_set():
                    break
                self._pause_gate.wait()
                if self._stop_flag.is_set():
                    break
                futures.append(executor.submit(_run_one, wm, bm))
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
            if len(item) == 6:
                white, black, result, duration, pgn_fen, move_count = item
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
                for pid in (w_id, b_id):
                    self._game_durations.setdefault(pid, []).append(duration)
            processed.append((white, black, result, duration, pgn_fen, move_count))
        return processed

    def process_moves(self) -> list[tuple]:
        """Drain the moves queue, update live board state.

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
            tid, board_copy, san, wm, bm = item
            with self._lock:
                fullmove = board_copy.fullmove_number
                side = "White" if board_copy.turn == chess.WHITE else "Black"
                self._live_sequence += 1
                self._live_state[tid] = (board_copy, san, wm, bm, fullmove, side, self._live_sequence)
            drained.append(item)
        return drained
