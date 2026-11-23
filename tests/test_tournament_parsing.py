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


def test_llm_presets_and_inline_flags_share_resolved_elo_id():
    from model_config import resolve_model_spec

    model, _ = resolve_model_spec("@qwen3-local")
    assert player_id("@qwen3-local") == player_id("@qwen3-local?retries=5") == player_id(model)


def test_single_game_explicit_flags_override_yaml_defaults(monkeypatch, tmp_path):
    import chess_llm

    players = []

    def fake_play(match):
        players.extend((match.white, match.black))
        return "1/2-1/2"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chess_llm.LLMPlayer, "check_connectivity", lambda self: True)
    monkeypatch.setattr(chess_llm.ChessMatch, "play", fake_play)
    monkeypatch.setattr(sys, "argv", [
        "chess_llm.py", "--model", "example/model", "--timeout", "60",
        "--black-flags", "timeout=90",
    ])
    chess_llm.main()
    assert [player.timeout for player in players] == [60, 90]


def test_tournament_global_flags_and_stockfish_path(monkeypatch, tmp_path):
    import chess_llm

    players = []

    def fake_play(match):
        players.extend((match.white, match.black))
        return "1/2-1/2"

    class FakeStockfish:
        def __init__(self, *, name, binary_path, **kwargs):
            self.name = name
            self.binary_path = binary_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chess_llm, "StockfishPlayer", FakeStockfish)
    monkeypatch.setattr(chess_llm.LLMPlayer, "check_connectivity", lambda self: True)
    monkeypatch.setattr(chess_llm.ChessMatch, "play", fake_play)
    monkeypatch.setattr(sys, "argv", [
        "tournament.py", "--gauntlet", "example/model", "--opponents", "stockfish:0",
        "--no-tui", "--tiny", "--timeout", "60", "--model-flags", "tools=on",
        "--stockfish-path", "/custom/stockfish",
    ])
    tournament.main()
    llm, stockfish = players[:2]
    assert llm.tiny is True
    assert llm.use_tools is False
    assert llm.timeout == 60
    assert stockfish.binary_path == "/custom/stockfish"


@pytest.mark.parametrize("flags,timeout", [({}, 240), ({"timeout": 120}, 120)])
def test_bigpickle_bumps_only_implicit_default_timeout(flags, timeout):
    _, player, _, _ = tournament.parse_player_spec("bigpickle/example", **flags)
    assert player.timeout == timeout


def test_tui_gauntlet_alternates_colours(monkeypatch):
    import tui.tournament

    captured = {}

    class FakeApp:
        def __init__(self, *, schedule, **kwargs):
            captured["pairs"] = [(game.white, game.black) for game in schedule]

        def run(self):
            pass

    monkeypatch.setattr(tui.tournament, "TournamentApp", FakeApp)
    monkeypatch.setattr(sys, "argv", [
        "tournament.py", "--gauntlet", "C", "--opponents", "A", "B",
        "--games", "2", "--tui",
    ])
    tournament.main()
    assert captured["pairs"] == [
        ("C", "A"), ("A", "C"), ("C", "A"), ("A", "C"),
        ("C", "B"), ("B", "C"), ("C", "B"), ("B", "C"),
    ]


@pytest.mark.parametrize("legacy", [False, True])
def test_plain_resume_without_players(monkeypatch, tmp_path, legacy):
    import json
    from tui.state import build_schedule, save_state

    path = str(tmp_path / "checkpoint.json")
    schedule = build_schedule(["random", "stockfish:0"], 1, "unbalanced")
    save_state(
        ["random", "stockfish:0"], 1, 0, 1, {"binary_path": "/custom/stockfish"},
        [("random", "stockfish:0", "1-0")], {}, None, 0,
        openings_mode="unbalanced", remaining_games=schedule[1:], path=path,
    )
    if legacy:
        checkpoint = Path(path)
        data = json.loads(checkpoint.read_text())
        del data["config"]["openings_mode"]
        del data["remaining_games"]
        checkpoint.write_text(json.dumps(data))

    calls = []

    def fake_match(white, black, **kwargs):
        calls.append((white, black, kwargs))
        return "1/2-1/2"

    monkeypatch.setattr(tournament, "run_match", fake_match)
    monkeypatch.setattr(sys, "argv", ["tournament.py", "--resume", path, "--no-tui"])
    tournament.main()

    [(white, black, kwargs)] = calls
    assert (white, black) == ("stockfish:0", "random")
    assert kwargs["binary_path"] == "/custom/stockfish"
    if legacy:
        assert kwargs["starting_board"] is None
    else:
        assert kwargs["opening_name"] == schedule[1].opening_name
        assert kwargs["starting_board"].fen() == schedule[1].starting_board().fen()
    assert not Path(path).exists()


def test_plain_resume_keeps_ratings_written_after_checkpoint(monkeypatch, tmp_path):
    """Resume applies new games to the live ratings file; it must not replace
    the file with the (older) checkpoint snapshot."""
    import json
    from tui.state import build_schedule, save_state

    db = tmp_path / "ratings.json"
    path = str(tmp_path / "checkpoint.json")
    schedule = build_schedule(["random", "stockfish:0"], 1, "standard")
    save_state(
        ["random", "stockfish:0"], 1, 0, 1, {}, [("random", "stockfish:0", "1-0")],
        {"random": {"rating": 1216, "games": 1, "wins": 1, "losses": 0, "draws": 0}},
        str(db), 0, remaining_games=schedule[1:], path=path,
    )
    # Another run rated a different player after the checkpoint was written.
    other = {"rating": 1300, "games": 4, "wins": 3, "losses": 1, "draws": 0}
    db.write_text(json.dumps({"someone-else": other}))

    monkeypatch.setattr(tournament, "run_match", lambda w, b, **kw: "1/2-1/2")
    monkeypatch.setattr(sys, "argv", ["tournament.py", "--resume", path, "--no-tui"])
    tournament.main()

    ratings = json.loads(db.read_text())
    assert ratings["someone-else"] == other
    assert ratings["random"]["games"] == 1  # only the resumed game was applied
    assert ratings["stockfish-0"]["draws"] == 1


def test_tui_resume_restores_openings_mode(monkeypatch, tmp_path):
    from tui.state import build_schedule, save_state
    from tui.tournament import TournamentApp

    path = str(tmp_path / "checkpoint.json")
    schedule = build_schedule(["a", "b"], 1, "unbalanced")
    save_state(
        ["a", "b"], 1, 0, 1, {}, [("a", "b", "1-0")], {}, None, 0,
        openings_mode="unbalanced", remaining_games=schedule[1:], path=path,
    )
    apps = []
    monkeypatch.setattr(TournamentApp, "run", lambda self: apps.append(self))
    monkeypatch.setattr(sys, "argv", ["tournament.py", "--resume", path, "--tui"])
    tournament.main()

    [app] = apps
    assert app.openings_mode == "unbalanced"
    assert app.runner.remaining_games() == schedule[1:]
    assert app.checkpoint_path == path
