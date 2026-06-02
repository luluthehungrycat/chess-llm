"""
Per-model configuration for chess-llm.

Supports three sources of model-specific settings, merged in priority order
(later overrides earlier):

  1. defaults in models.yaml
  2. named presets in models.yaml (referenced as @preset-name)
  3. inline query flags on the model string (model?key=val&key=val)
  4. CLI per-player flags (--white-flags, --black-flags, --player-flags)

Usage:
    from model_config import ModelConfig, resolve_model_spec

    # Resolve @preset references and query-param overrides
    model_name, overrides = resolve_model_spec("@qwen3-local")
    model_name, overrides = resolve_model_spec("llama-cpp/model?tiny=1&retries=10")

    # Load the full config
    cfg = ModelConfig.load()
    preset = cfg.get_preset("qwen3-local")
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml


# ── Known flag names (mapped to LLMPlayer.__init__ kwargs) ──────────
# These are the keys recognised in model configs and query params.
# Anything in defaults.yml under these names is passed to LLMPlayer().
FLAG_MAP = {
    "use_tools":     "use_tools",
    "tools":         "use_tools",       # alias: tools=on/off
    "tiny":          "tiny",
    "constrain":     "constrain",       # force legal via closest-match
    "max_retries":   "max_retries",
    "retries":       "max_retries",     # alias
    "temperature":   "temperature",
    "temp":          "temperature",     # alias
    "timeout":       "timeout",
    "reasoning":     "reasoning",
}

# Boolean flags that accept "on"/"off"/"true"/"false"/"1"/"0"
_BOOL_FLAGS = {"use_tools", "tools", "tiny"}


def _coerce_bool(value: Any) -> Any:
    """Convert human-friendly bool strings to Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "on", "1"):
            return True
        if v in ("false", "no", "off", "0"):
            return False
    return value


def _parse_query_flags(query_string: str) -> dict[str, Any]:
    """
    Parse model?key=val&key=val or CLI "key=val,key=val" into a dict of LLMPlayer kwargs.

    Splits on & and , as separators.
    Boolean flags accept: on/off/true/false/1/0
    Numeric flags are cast to int or float.
    Unknown keys are silently ignored.
    """
    overrides: dict[str, Any] = {}
    if not query_string:
        return overrides

    # Split on both & and , for CLI-friendly comma-separated syntax
    parts = []
    for chunk in query_string.split("&"):
        parts.extend(chunk.split(","))

    for part in parts:
        part = part.strip()
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip().lower()
        val = val.strip()

        if key not in FLAG_MAP:
            continue

        mapped = FLAG_MAP[key]
        val = _coerce_bool(val)

        # Cast numeric strings
        if isinstance(val, str) and mapped in ("temperature", "timeout", "max_retries"):
            try:
                if "." in val:
                    val = float(val)
                else:
                    val = int(val)
            except ValueError:
                pass

        overrides[mapped] = val

    return overrides


# Regex: match @preset-name or plain model, optionally followed by ?query
_SPEC_RE = re.compile(
    r"^@(?P<preset>[a-zA-Z0-9_.-]+)(?:\?(?P<query>.*))?$"
    r"|"
    r"^(?P<model>[^?]+?)(?:\?(?P<model_query>.*))?$"
)


def resolve_model_spec(spec: str) -> tuple[str, dict[str, Any]]:
    """
    Resolve a player spec string into (model_name, overrides_dict).

    Handles:
      - @preset-name          → looks up preset in models.yaml
      - @preset-name?tiny=1   → preset + inline override
      - llama-cpp/model       → raw model string, no overrides
      - model?tools=off&retries=10 → raw model + inline overrides

    Returns (model_name, {overrides}) where model_name never starts with @.
    """
    cfg = ModelConfig.load()
    m = _SPEC_RE.match(spec.strip())

    if not m:
        return spec, {}

    if m.group("preset"):
        # @preset-name[?query]
        preset = cfg.get_preset(m.group("preset"))
        if preset is None:
            raise ValueError(
                f"Unknown preset '@{m.group('preset')}'. "
                f"Known presets: {', '.join(cfg.list_presets()) or '(none)'}"
            )
        model = preset.get("model", "")
        overrides = {k: v for k, v in preset.items() if k != "model" and k in FLAG_MAP.values()}
        # Merge inline query flags on top
        query = m.group("query") or ""
        overrides.update(_parse_query_flags(query))
        return model, overrides

    # Plain model (with or without query string)
    model = m.group("model")
    query = m.group("model_query") or ""
    return model, _parse_query_flags(query)


class ModelConfig:
    """Loads and caches models.yaml from the chess-llm directory."""

    _instance: Optional["ModelConfig"] = None

    def __init__(self, data: dict[str, Any]):
        self._defaults: dict[str, Any] = data.get("defaults", {})
        self._presets: dict[str, dict[str, Any]] = data.get("presets", {})

    @classmethod
    def _config_path(cls) -> Path:
        """Find models.yaml next to this module (repo root)."""
        return Path(__file__).resolve().parent / "models.yaml"

    @classmethod
    def load(cls) -> "ModelConfig":
        """Load from disk, caching the result."""
        if cls._instance is not None:
            return cls._instance
        path = cls._config_path()
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        cls._instance = cls(data)
        return cls._instance

    @classmethod
    def reload(cls) -> "ModelConfig":
        """Force re-read from disk."""
        cls._instance = None
        return cls.load()

    def get_defaults(self) -> dict[str, Any]:
        """Return the [defaults] section as LLMPlayer kwargs."""
        return {
            FLAG_MAP.get(k, k): _coerce_bool(v)
            for k, v in self._defaults.items()
            if k in FLAG_MAP or k in FLAG_MAP.values()
        }

    def get_preset(self, name: str) -> Optional[dict[str, Any]]:
        """Return the raw preset dict, or None if not found."""
        return self._presets.get(name)

    def list_presets(self) -> list[str]:
        """Return sorted list of preset names."""
        return sorted(self._presets.keys())
