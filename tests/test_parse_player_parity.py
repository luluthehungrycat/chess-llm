"""Test parse_player (chess_llm.py) and parse_player_spec (tournament.py).

These two entry points interpret the same spec string, so they must
produce equivalent LLMPlayer kwargs for equivalent specs. This test
file locks down the parity — including the case that the --constrain
flag works for both single games AND tournaments.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chess_llm import parse_player
from tournament import parse_player_spec


# ── Parity: both parsers must produce equivalent kwargs ────────────────

@pytest.mark.parametrize("spec", [
    "bigpickle/nemotron-3-super-free",
    "openai/gpt-4o",
    "ollama/llama3",
    "anthropic/claude-sonnet-4",
    "random",
    "stockfish",
    "stockfish:10",
    "human",
    "human:Alice",
])
def test_parse_parity_for_basic_specs(spec):
    """parse_player and parse_player_spec must agree on player type."""
    ptype_a, kwargs_a = parse_player(spec)
    ptype_b, _, _, _ = parse_player_spec(spec)
    assert ptype_a == ptype_b, f"type mismatch for {spec}: {ptype_a!r} vs {ptype_b!r}"


@pytest.mark.parametrize("spec,query_key,query_val", [
    ("bigpickle/nemotron-3-super-free", "constrain", "1"),
    ("bigpickle/nemotron-3-super-free", "tiny", "true"),
    ("openai/gpt-4o", "retries", "5"),
    ("openai/gpt-4o", "temperature", "0.7"),
    ("openai/gpt-4o", "timeout", "180"),
    ("openai/gpt-4o", "reasoning", "low"),
])
def test_inline_query_flag_propagates_through_both_parsers(spec, query_key, query_val):
    """Inline ?key=val must propagate to LLMPlayer kwargs in BOTH paths.

    Regression: --constrain was silently dropped by parse_player while
    parse_player_spec forwarded it, causing divergent behavior between
    `chess_llm.py -w X?constrain=1` and `tournament.py -w X?constrain=1`.
    """
    full_spec = f"{spec}?{query_key}={query_val}"
    ptype_a, kwargs_a = parse_player(full_spec)
    ptype_b, _, _, overrides_b = parse_player_spec(full_spec)

    assert ptype_a == "llm", f"expected llm type for {full_spec}, got {ptype_a}"
    # map query_key to the internal LLMPlayer kwarg name (mirrors FLAG_MAP)
    flag_map = {
        "constrain": "constrain",
        "tiny": "tiny",
        "retries": "max_retries",
        "temperature": "temperature",
        "timeout": "timeout",
        "reasoning": "reasoning",
    }
    internal = flag_map[query_key]
    assert kwargs_a.get(internal) is not None, (
        f"parse_player dropped {query_key}={query_val} for {spec}: "
        f"kwargs={kwargs_a}"
    )
    assert overrides_b.get(internal) is not None, (
        f"parse_player_spec dropped {query_key}={query_val} for {spec}: "
        f"overrides={overrides_b}"
    )


def test_constrain_propagates_for_single_game():
    """--constrain must work for `chess_llm.py -w X?constrain=1`."""
    ptype, kwargs = parse_player("bigpickle/nemotron-3-super-free?constrain=1")
    assert ptype == "llm"
    assert kwargs.get("constrain") is True


def test_constrain_propagates_for_tournament():
    """--constrain must work for `tournament.py -w X?constrain=1`."""
    ptype, player, label, overrides = parse_player_spec(
        "bigpickle/nemotron-3-super-free?constrain=1"
    )
    assert ptype == "llm"
    assert overrides.get("constrain") is True
    assert getattr(player, "constrain", None) is True


def test_tiny_forces_no_tools():
    """tiny=true must force use_tools=False in BOTH parsers."""
    ptype_a, kwargs_a = parse_player("ollama/llama3?tiny=true")
    ptype_b, _, _, overrides_b = parse_player_spec("ollama/llama3?tiny=true")
    assert kwargs_a.get("use_tools") is False
    assert kwargs_a.get("tiny") is True
    assert overrides_b.get("use_tools") is False
    assert overrides_b.get("tiny") is True


def test_unknown_query_flag_silently_ignored():
    """Unknown query keys are dropped (not an error)."""
    ptype, kwargs = parse_player("openai/gpt-4o?unknown_flag=42")
    assert ptype == "llm"
    assert "unknown_flag" not in kwargs


def test_preset_overrides_inline():
    """A named preset's values can be overridden inline by ?key=val."""
    ptype, kwargs = parse_player("@big-pickle?retries=99")
    # big-pickle preset defaults max_retries=5
    assert kwargs.get("max_retries") == 99
