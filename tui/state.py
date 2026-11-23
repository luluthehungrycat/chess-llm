"""Tournament state persistence — save/resume support."""

from collections import Counter
import json
import os
import tempfile
import time
from pathlib import Path
from typing import NamedTuple, Optional

import chess


STATE_FILE = "tournament_state.json"


def save_state(
    models: list[str],
    games_per_pair: int,
    delay: float,
    max_workers: int,
    player_kwargs: dict,
    completed: list[tuple[str, str, str]],
    elo_ratings: dict,
    elo_db_path: Optional[str],
    started_at: float,
    *,
    openings_mode: str = "standard",
    remaining_games: list["ScheduledGame"] | None = None,
    path: str = STATE_FILE,
):
    """Save tournament progress so it can be resumed later."""
    state = {
        "config": {
            "models": models,
            "games_per_pair": games_per_pair,
            "delay": delay,
            "max_workers": max_workers,
            "player_kwargs": player_kwargs,
            "elo_db_path": elo_db_path,
            "openings_mode": openings_mode,
        },
        "completed": [[w, b, r] for w, b, r in completed],
        "elo_ratings": elo_ratings,
        "started_at": started_at,
        "saved_at": time.time(),
        "elapsed_seconds": time.time() - started_at,
    }
    if remaining_games is not None:
        state["remaining_games"] = remaining_games
    with tempfile.NamedTemporaryFile(
        mode="w", dir=Path(path).parent, delete=False, encoding="utf-8"
    ) as f:
        temporary_path = f.name
        try:
            json.dump(state, f, indent=2)
            f.close()
            os.replace(temporary_path, path)
        finally:
            Path(temporary_path).unlink(missing_ok=True)
    return path


def load_state(path: str = STATE_FILE) -> dict | None:
    """Load a saved tournament state, or None if no save exists."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def clear_state(path: str = STATE_FILE):
    """Remove the saved state file (called on clean completion)."""
    Path(path).unlink(missing_ok=True)


class ScheduledGame(NamedTuple):
    white: str
    black: str
    opening_name: str = ""
    opening_moves: tuple[str, ...] = ()

    def starting_board(self) -> chess.Board | None:
        if not self.opening_moves:
            return None
        board = chess.Board()
        for move in self.opening_moves:
            board.push_uci(move)
        return board


def build_schedule(
    models: list[str],
    games_per_pair: int,
    openings_mode: str = "standard",
    *,
    gauntlet: bool = False,
) -> list[ScheduledGame]:
    """Assign colours and openings in the order games will be submitted."""
    if gauntlet:
        champion, *opponents = models
        pairs = (
            pair for opponent in opponents for _ in range(games_per_pair)
            for pair in ((champion, opponent), (opponent, champion))
        )
    else:
        pairs = (
            (white, black) for i, white in enumerate(models)
            for j, black in enumerate(models) if i != j
            for _ in range(games_per_pair)
        )

    if openings_mode != "unbalanced":
        return [ScheduledGame(white, black) for white, black in pairs]

    from itertools import cycle
    from openings import OPENINGS

    return [
        ScheduledGame(white, black, name, tuple(moves))
        for (white, black), (name, moves, _) in zip(pairs, cycle(OPENINGS))
    ]


def restore_schedule(state: dict) -> list[ScheduledGame]:
    """Restore pending games, or reconstruct the schedule of a legacy save."""
    if "remaining_games" in state:
        return [
            ScheduledGame(white, black, name, tuple(moves))
            for white, black, name, moves in state["remaining_games"]
        ]
    config = state["config"]
    return _subtract_completed(
        build_schedule(
            config["models"], config["games_per_pair"],
            config.get("openings_mode", "standard"),
        ),
        state["completed"],
    )


def compute_remaining_tasks(
    models: list[str],
    games_per_pair: int,
    completed: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """Return remaining white/black pairings for a round robin."""
    schedule = _subtract_completed(build_schedule(models, games_per_pair), completed)
    return [(game.white, game.black) for game in schedule]


def _subtract_completed(schedule, completed):
    done = Counter((white, black) for white, black, result in completed if result != "error")
    remaining = []
    for game in schedule:
        pair = (game.white, game.black)
        if done[pair]:
            done[pair] -= 1
        else:
            remaining.append(game)
    return remaining
