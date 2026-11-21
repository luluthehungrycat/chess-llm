"""tournament.py uses chess_llm.parse_player and one ELO-id scheme."""

import subprocess
import sys
from pathlib import Path

import pytest

import tournament
from elo import player_id

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("spec", [
    "random", "human:Alice", "stockfish:5", "@stockfish-0", "@qwen3-local",
    "openai/gpt-4o?retries=5",
])
def test_run_match_label_equals_parallel_elo_id(spec):
    """Sequential (label) and parallel/TUI (player_id) paths must agree,
    otherwise one player collects two separate ratings."""
    _, _, label, _ = tournament.parse_player_spec(spec)
    assert label == player_id(spec)


def test_preset_resolves_to_stockfish_player():
    ptype, player, _, _ = tournament.parse_player_spec("@stockfish-0")
    assert ptype == "stockfish"
    assert player.skill_level == 0


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="Unknown preset"):
        tournament.parse_player_spec("@no-such-preset")


def _run(*argv):
    return subprocess.run(
        [sys.executable, "tournament.py", *argv],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


def test_cli_unknown_preset_exits_2():
    proc = _run("--round-robin", "random", "@no-such-preset", "--no-tui")
    assert proc.returncode == 2
    assert "Unknown preset" in proc.stderr


def test_stockfish_skill_applies_to_bare_stockfish(monkeypatch):
    seen = {}

    def fake_round_robin(models, **kw):
        seen["models"] = models

    monkeypatch.setattr(tournament, "round_robin", fake_round_robin)
    monkeypatch.setattr(sys, "argv", [
        "tournament.py", "--round-robin", "stockfish", "stockfish:3", "random",
        "--stockfish-skill", "7", "--no-tui",
    ])
    tournament.main()
    assert seen["models"] == ["stockfish:7", "stockfish:3", "random"]


def test_explicit_tui_failure_is_not_swallowed(monkeypatch):
    """--tui was asked for explicitly, so a startup error must surface
    instead of silently falling back to plain-text mode."""
    monkeypatch.setitem(sys.modules, "tui.tournament", None)  # import fails
    monkeypatch.setattr(sys, "argv", [
        "tournament.py", "--round-robin", "random", "stockfish:1", "--tui",
    ])
    with pytest.raises(ImportError):
        tournament.main()


@pytest.mark.parametrize("a,b", [
    ("@stockfish-0", "stockfish:0"),
    ("stockfish", "stockfish:20"),
    ("human", "human:Human"),
])
def test_aliases_share_one_elo_id(a, b):
    assert player_id(a) == player_id(b)
