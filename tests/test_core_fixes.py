"""Regression tests for core reliability fixes in chess_llm.py."""

import time

import chess
import pytest

import chess_llm
from chess_llm import ChessMatch, _extract_move, _run_with_timeout


# ── Hard timeout ─────────────────────────────────────────────────────────────

def test_timeout_returns_promptly_even_if_call_hangs():
    """A hung call must not block past the timeout (the old
    `with ThreadPoolExecutor()` waited for the worker on exit)."""
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        _run_with_timeout(time.sleep, 0.2, 5)
    assert time.monotonic() - start < 2


def test_timeout_propagates_worker_exceptions():
    def boom():
        raise ValueError("provider exploded")

    with pytest.raises(ValueError, match="provider exploded"):
        _run_with_timeout(boom, 5)


def test_timeout_returns_value():
    assert _run_with_timeout(lambda x: x * 2, 5, 21) == 42


def test_call_llm_raises_timeout_without_waiting_for_hung_provider(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion", lambda **kw: time.sleep(10))
    start = time.monotonic()
    # timeout + 15 is the hard limit; use a negative base to keep the test fast
    with pytest.raises(TimeoutError, match="No response"):
        chess_llm._call_llm("openai/x", "sys", [], timeout=-14.5)
    assert time.monotonic() - start < 3


# ── MOVE: marker extraction ──────────────────────────────────────────────────

def test_illegal_marker_falls_through_to_later_legal_move():
    board = chess.Board()
    text = "MOVE: e2e5 — wait, that's illegal. Correct move: MOVE: e2e4"
    assert _extract_move(text, board) == "e2e4"


def test_illegal_marker_then_raw_legal_uci():
    board = chess.Board()
    assert _extract_move("MOVE: e2e5\nactually g1f3", board) == "g1f3"


def test_only_illegal_marker_is_returned_for_explanation():
    board = chess.Board()
    # Caller relies on getting the illegal move back to explain the error
    assert _extract_move("MOVE: e2e5", board) == "e2e5"


def test_legal_marker_still_wins():
    board = chess.Board()
    assert _extract_move("e2e4 is tempting but MOVE: d2d4", board) == "d2d4"


# ── Engine cleanup ───────────────────────────────────────────────────────────

class _Exploding:
    name = "Exploding"

    def get_move(self, board, history):
        raise RuntimeError("player crashed")


class _Closable:
    name = "Closable"

    def __init__(self):
        self.closed = 0

    def get_move(self, board, history):
        return next(iter(board.legal_moves))

    def close(self):
        self.closed += 1


def test_engines_closed_when_player_raises():
    engine = _Closable()
    match = ChessMatch(_Exploding(), engine, delay=0)
    with pytest.raises(RuntimeError):
        match.play()
    assert engine.closed == 1


def test_engines_closed_on_keyboard_interrupt():
    class _Interrupt(_Exploding):
        def get_move(self, board, history):
            raise KeyboardInterrupt

    engine = _Closable()
    match = ChessMatch(_Interrupt(), engine, delay=0)
    with pytest.raises(KeyboardInterrupt):
        match.play()
    assert engine.closed == 1


def test_correction_after_illegal_marker_beats_earlier_mention():
    board = chess.Board()
    text = "I considered e2e4. MOVE: e2e5. Actually Nf3"
    assert _extract_move(text, board) == "g1f3"


def test_cleanup_closes_both_engines_and_keeps_original_error():
    class _BadClose(_Closable):
        def close(self):
            super().close()
            raise OSError("engine pipe broken")

    class _ExplodingBadClose(_Exploding, _BadClose):
        pass

    white = _ExplodingBadClose()
    black = _Closable()
    match = ChessMatch(white, black, delay=0)
    with pytest.raises(RuntimeError, match="player crashed"):
        match.play()
    assert white.closed == 1 and black.closed == 1


def test_single_game_self_play_with_elo_does_not_crash(tmp_path):
    import subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, str(root / "chess_llm.py"), "-w", "random", "-b", "random",
         "--delay", "0", "--elo", "--elo-db", str(tmp_path / "r.json")],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
