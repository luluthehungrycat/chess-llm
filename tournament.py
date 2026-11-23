#!/usr/bin/env python3
"""
Tournament runner for LLM Chess.

Runs round-robin or gauntlet tournaments between models, tracking ELO.
Imports chess_llm's player classes and match engine directly.

Usage:
    # Round-robin: every model plays every other (both colors)
    python tournament.py --round-robin model-a model-b model-c

    # Gauntlet: one model plays against all others
    python tournament.py --gauntlet champion --opponents challenger1 challenger2

    # With ELO tracking and custom settings
    python tournament.py --round-robin docker/ai/qwen3.5:9B \
        docker/ai/ministral3:3B stockfish --elo --no-tools --delay 0
"""

import argparse
import concurrent.futures
import datetime
import os
import sys
import time
from itertools import count
from pathlib import Path
from typing import Optional

# Add parent to path so we can import chess_llm modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elo import EloTracker, player_id
from chess_llm import ChessMatch
from tui.state import STATE_FILE, build_schedule, clear_state, load_state, restore_schedule, save_state


class _LiveChessMatch(ChessMatch):
    """Expose committed moves at the match's turn and completion boundaries."""

    def __init__(self, *args, on_move, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_move = on_move
        self._reported_plies = len(self.board.move_stack)

    def _report_move(self):
        plies = len(self.board.move_stack)
        if plies > self._reported_plies:
            self._reported_plies = plies
            self._on_move(self.board, self.node.san(), self.board.peek())

    def _history_text(self):
        self._report_move()
        return super()._history_text()

    def play(self):
        result = super().play()
        self._report_move()
        return result


def parse_player_spec(
    spec: str, *, model_flags: str | None = None, binary_path: str | None = None,
    think_time: float = 0.1, threads: int | None = None, **global_flags,
):
    """Return (player type, player, ELO ID, merged LLM options)."""
    from chess_llm import (HumanPlayer, LLMPlayer, LLM_PLAYER_KWARGS, RandomPlayer,
                           StockfishPlayer, parse_player)

    ptype, kwargs = parse_player(
        spec, global_flags=global_flags, per_player_flags=model_flags,
    )
    elo_id = player_id(spec)
    if ptype == "human":
        return ptype, HumanPlayer(name=kwargs["name"]), elo_id, {}
    if ptype == "random":
        return ptype, RandomPlayer(name="Random"), elo_id, {}
    if ptype == "stockfish":
        player = StockfishPlayer(
            name=kwargs["name"], skill_level=kwargs["skill"],
            binary_path=binary_path, think_time=think_time, threads=threads,
        )
        return ptype, player, elo_id, {}
    options = {k: v for k, v in kwargs.items() if k in LLM_PLAYER_KWARGS}
    return ptype, LLMPlayer(**kwargs), elo_id, options


# Kept as a name for existing callers; the logic lives in elo.player_id.
_elo_id_from_spec = player_id


def run_match(white_spec: str, black_spec: str,
              delay: float = 0.5,
              elo_tracker: Optional[EloTracker] = None,
              log_dir: Optional[str] = None,
              starting_board = None,
              opening_name: str = "",
              on_move=None,
              quiet: bool = False,
              **player_kwargs) -> str:
    """Run a single match. Returns result string ('1-0', '0-1', '1/2-1/2')."""
    _, white, w_id, _ = parse_player_spec(white_spec, **player_kwargs)
    _, black, b_id, _ = parse_player_spec(black_spec, **player_kwargs)

    # Pre-flight
    for p in (white, black):
        if hasattr(p, "check_connectivity"):
            try:
                p.check_connectivity()
            except Exception as e:
                print(f"   ⚠ {p.name}: connectivity check failed: {e}")

    if not quiet:
        print(f"\n{'=' * 50}")
        print(f"  {white.name} (White)  vs  {black.name} (Black)")
        if starting_board is not None and opening_name:
            print(f"  Opening: {opening_name}")
        print(f"{'=' * 50}")

    if on_move is None:
        match = ChessMatch(white, black, delay=delay, starting_board=starting_board)
    else:
        match = _LiveChessMatch(white, black, delay=delay, starting_board=starting_board,
                                on_move=on_move)
    result = match.play()

    # Save PGN
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    w_name = white.name.replace("/", "_").replace(" ", "_")[:40]
    b_name = black.name.replace("/", "_").replace(" ", "_")[:40]
    games_dir = "games"
    os.makedirs(games_dir, exist_ok=True)
    stem = f"{ts}_{w_name}_vs_{b_name}"
    for index in count():
        suffix = f"_{index}" if index else ""
        pgn_path = Path(games_dir) / f"{stem}{suffix}.pgn"
        try:
            pgn_file = pgn_path.open("x", encoding="utf-8")
        except FileExistsError:
            continue
        with pgn_file:
            print(match.pgn_game, file=pgn_file)
        break
    if not quiet:
        print(f"\n📄 PGN saved to {pgn_path}")

    # ELO
    if elo_tracker:
        updated = elo_tracker.update(w_id, b_id, result)
        print(f"  ELO: {w_id} → {updated['white']['rating']}  |  "
              f"{b_id} → {updated['black']['rating']}")

    return result


def _run_schedule(
    schedule, delay, elo_tracker, max_workers, player_kwargs,
    *, sequential_pause=0, on_result=None,
):
    """Run scheduled games, applying ratings and progress on the main thread."""
    started = time.monotonic()
    results = []

    def play(game, tracker=None):
        try:
            result = run_match(
                game.white, game.black, delay=delay, elo_tracker=tracker,
                starting_board=game.starting_board(), opening_name=game.opening_name,
                **player_kwargs,
            )
            return result, None
        except Exception as exc:
            return "error", str(exc)

    def collect(index, outcome):
        game = schedule[index]
        result, error = outcome
        results.append((game.white, game.black, result))
        if error is not None:
            print(f"  ❌ Match failed: {error}")
        if on_result is not None:
            on_result(index, result)

    if max_workers <= 1:
        for index, game in enumerate(schedule):
            print(f"\n── Game {index + 1}/{len(schedule)}: {game.white} vs {game.black} ──")
            collect(index, play(game, elo_tracker))
            if sequential_pause:
                time.sleep(sequential_pause)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(play, game): i for i, game in enumerate(schedule)}
            for future in concurrent.futures.as_completed(futures):
                collect(futures[future], future.result())
                white, black, result = results[-1]
                print(f"  ⚡ [{len(results)}/{len(schedule)}] {white} vs {black} → {result}")

        if elo_tracker:
            for white, black, result in results:
                if result != "error":
                    elo_tracker.update(_elo_id_from_spec(white), _elo_id_from_spec(black), result)

    print(f"\n  Tournament finished in {time.monotonic() - started:.0f}s")
    print(f"  Games: {len(results)}")
    if elo_tracker:
        elo_tracker.print_leaderboard()
    return results


def round_robin(models: list[str], games_per_pair: int = 1,
                delay: float = 0.5, elo_tracker: Optional[EloTracker] = None,
                max_workers: int = 1, openings_mode: str = "standard",
                **player_kwargs):
    """Play each pair in both colours."""
    print(f"\n🏟  Round-Robin Tournament: {', '.join(models)}")
    schedule = build_schedule(models, games_per_pair, openings_mode)
    return _run_schedule(
        schedule, delay, elo_tracker, max_workers, player_kwargs, sequential_pause=0.5,
    )


def gauntlet(champion: str, opponents: list[str],
             games_per_opponent: int = 1, delay: float = 0.5,
             elo_tracker: Optional[EloTracker] = None,
             max_workers: int = 1, openings_mode: str = "standard", **player_kwargs):
    """Play the champion against each opponent, alternating colours."""
    print(f"\n🏟  Gauntlet: {champion} vs {', '.join(opponents)}")
    schedule = build_schedule(
        [champion, *opponents], games_per_opponent, openings_mode, gauntlet=True,
    )
    return _run_schedule(schedule, delay, elo_tracker, max_workers, player_kwargs)


def _resume_plain(state, config, schedule, path):
    """Resume a checkpoint using its ratings snapshot and pending games."""
    completed = [tuple(game) for game in state["completed"] if game[2] != "error"]
    elo_db = config.get("elo_db_path")
    # The live ratings file is the source of truth: each new game is applied
    # to it as it finishes. Overwriting it with the checkpoint snapshot would
    # erase ratings recorded since the checkpoint was written.
    if elo_db:
        tracker = EloTracker(elo_db)
    else:
        tracker = EloTracker(":memory:")
        tracker._ratings = state.get("elo_ratings", {})
    finished = set()

    def record(index, result):
        if result == "error":
            return
        game = schedule[index]
        tracker.update(player_id(game.white), player_id(game.black), result)
        finished.add(index)
        completed.append((game.white, game.black, result))
        save_state(
            config["models"], config["games_per_pair"], config["delay"],
            config["max_workers"], config["player_kwargs"], completed,
            tracker._ratings, elo_db, state["started_at"],
            openings_mode=config.get("openings_mode", "standard"),
            remaining_games=[game for i, game in enumerate(schedule) if i not in finished],
            path=path,
        )

    results = _run_schedule(
        schedule, config["delay"], None, config["max_workers"],
        config["player_kwargs"], on_result=record,
    )
    if elo_db:
        tracker.print_leaderboard()
    if len(finished) == len(schedule):
        clear_state(path)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="LLM Chess Tournament Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  # Local models via Docker:\n"
               "  python tournament.py --round-robin stockfish docker/ai/qwen3.5:9B docker/ai/ministral3:3B\n"
               "  python tournament.py --gauntlet docker/ai/qwen3.5:9B --opponents stockfish random\n"
               "  # Free cloud models via Big Pickle Proxy:\n"
               "  python tournament.py --round-robin bigpickle/big-pickle bigpickle/deepseek-v4-flash-free \\\n"
               "      bigpickle/nemotron-3-super-free bigpickle/mimo-v2.5-free --reasoning low\n"
               "  python tournament.py --gauntlet bigpickle/big-pickle \\\n"
               "      --opponents bigpickle/deepseek-v4-flash-free stockfish:0 --elo --delay 0",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--round-robin", nargs="+", metavar="MODEL",
                      help="Round-robin: every model plays every other (both colors)")
    mode.add_argument("--gauntlet", metavar="CHAMPION",
                      help="Gauntlet: champion plays all opponents")

    parser.add_argument("--opponents", nargs="+", metavar="MODEL",
                        help="Opponents for gauntlet mode")
    parser.add_argument("--games", type=int, default=1,
                        help="Games per pair (default: 1)")
    parser.add_argument("--parallel", type=int, default=1, metavar="N",
                        help="Run N games in parallel (default: 1, sequential). "
                             "When >1 and --elo is set, ELO is batch-computed at the end.")
    parser.add_argument("--openings", choices=["standard", "unbalanced"],
                        default="standard",
                        help="Opening mode: 'standard' (from start position) or "
                             "'unbalanced' (pre-played lines that favor one side, "
                             "reducing draw rates in engine tournaments)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between moves in seconds (default: 0.5)")
    parser.add_argument("--elo", action="store_true",
                        help="Track ELO ratings")
    parser.add_argument("--elo-db", default="ratings.json")
    parser.add_argument("--no-tools", action="store_true", default=None,
                        help="Disable tool calling for LLM players")
    parser.add_argument("--tiny", action="store_true", default=None,
                        help="Tiny-model mode: compact UCI-only prompt for models <20B. "
                             "Forces --no-tools, strips FEN, uses strict MOVE: <uci> format.")
    parser.add_argument("--constrain", action="store_true", default=None,
                        help="Force legal moves: when the model proposes an illegal move, "
                             "pick the closest legal move instead of retrying or forfeiting.")
    parser.add_argument("--reasoning", choices=["low", "medium", "high", "none"],
                        default=None,
                        help="Reasoning effort for providers that support it "
                             "(OpenRouter/OpenAI: reasoning_effort; Anthropic: thinking budget). "
                             "Use \"none\" to skip reasoning. Omit for provider default.")
    parser.add_argument("--retries", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--model-flags", type=str, default=None,
                        help="Comma-separated key=val flags applied to ALL LLM players "
                             "(e.g. tools=off,tiny=true,retries=10). "
                             "Overrides global flags and model settings.")
    parser.add_argument("--stockfish-skill", type=int, default=20)
    parser.add_argument("--stockfish-time", type=float, default=0.1)
    parser.add_argument("--stockfish-path",
                        help="Path to stockfish binary (default: auto-detect from PATH or common locations)")
    parser.add_argument(
        "--stockfish-threads", type=int, default=None,
        help="Number of CPU threads for Stockfish (default: use all cores). "
             "Set to 1 or 2 to keep the fan quiet during tournaments.",
    )

    # ── TUI ───────────────────────────────────────────────────────────
    tui_group = parser.add_mutually_exclusive_group()
    tui_group.add_argument("--tui", action="store_true", default=None,
                           help="Force TUI dashboard mode")
    tui_group.add_argument("--no-tui", action="store_true", default=None,
                           help="Force plain text mode (no dashboard)")

    # ── Resume / log ──────────────────────────────────────────────────
    parser.add_argument("--resume", nargs="?", const=STATE_FILE, metavar="CHECKPOINT",
                        help=f"Resume a saved tournament (default checkpoint: {STATE_FILE})")
    parser.add_argument("--log", "-l", nargs="?", const="auto", default=None,
                        help="Tee output to a log file (auto-names by date; or give a path)")

    args = parser.parse_args()
    if not (args.resume or args.round_robin or args.gauntlet):
        parser.error("provide --round-robin, --gauntlet, or --resume")
    if not args.resume and args.gauntlet and not args.opponents:
        parser.error("--gauntlet requires --opponents")

    # ── Log file tee (for non-TUI mode) ───────────────────────────────
    if args.log and not sys.stdout.isatty():
        import datetime as _dt
        if args.log == "auto":
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".logs")
            os.makedirs(log_dir, exist_ok=True)
            args.log = os.path.join(log_dir, f"tournament_{ts}.txt")
        # Tee stdout to log file
        _log_file = open(args.log, "w", buffering=1)
        _orig_stdout = sys.stdout
        class _Tee:
            def write(self, data):
                _orig_stdout.write(data)
                _log_file.write(data)
            def flush(self):
                _orig_stdout.flush()
                _log_file.flush()
        sys.stdout = _Tee()
        print(f"📝 Logging to {args.log}")

    # ── Normalise and validate player specs up front ──────────────────
    # Bare "stockfish" takes --stockfish-skill; rewriting the spec keeps the
    # player, its label and its ELO id in agreement everywhere downstream.
    def _normalise(spec: str) -> str:
        if spec.strip().lower() in ("stockfish", "stockfish:"):
            return f"stockfish:{args.stockfish_skill}"
        return spec

    if args.round_robin:
        args.round_robin = [_normalise(s) for s in args.round_robin]
    if args.gauntlet:
        args.gauntlet = _normalise(args.gauntlet)
    if args.opponents:
        args.opponents = [_normalise(s) for s in args.opponents]

    from chess_llm import parse_player
    for spec in (args.round_robin or []) + [args.gauntlet] * bool(args.gauntlet) + (args.opponents or []):
        try:
            parse_player(spec)
        except ValueError as e:
            parser.error(str(e))

    # Auto-detect TUI: use when stdout is a terminal unless explicitly disabled
    use_tui = args.tui if args.tui is not None else (
        sys.stdout.isatty() and args.no_tui is not True
    )

    if args.resume:
        try:
            state = load_state(args.resume)
            if state is None:
                parser.error(f"checkpoint not found: {args.resume}")
            config = state["config"]
            config.setdefault("openings_mode", "standard")
            schedule = restore_schedule(state)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            parser.error(f"could not load checkpoint {args.resume}: {exc}")
        print(f"📂 Resuming tournament: {len(schedule)} games remaining")
    else:
        state = None
        config = dict(
            models=args.round_robin or [args.gauntlet, *args.opponents],
            games_per_pair=args.games,
            delay=args.delay,
            max_workers=max(args.parallel, 1),
            openings_mode=args.openings,
            elo_db_path=args.elo_db if args.elo else None,
            player_kwargs=dict(
                use_tools=False if args.no_tools else None,
                max_retries=args.retries,
                temperature=args.temperature,
                timeout=args.timeout,
                tiny=args.tiny,
                reasoning=args.reasoning,
                constrain=args.constrain,
                model_flags=args.model_flags,
                threads=args.stockfish_threads,
                think_time=args.stockfish_time,
                binary_path=args.stockfish_path,
            ),
        )

    if use_tui:
        try:
            from tui.tournament import TournamentApp

            if state is None:
                schedule = build_schedule(
                    config["models"], args.games, args.openings, gauntlet=bool(args.gauntlet),
                )
            app = TournamentApp(
                **config,
                schedule=schedule,
                resume_completed=[tuple(game) for game in state["completed"]] if state else None,
                resume_elo=state.get("elo_ratings", {}) if state else None,
                checkpoint_path=args.resume or STATE_FILE,
            )
            app.run()
            return
        except Exception as e:
            if args.tui:
                raise
            print(f"⚠ TUI failed to start: {e}", file=sys.stderr)
            print("Falling back to plain-text mode. Use --no-tui to skip this warning.", file=sys.stderr)

    if state is not None:
        _resume_plain(state, config, schedule, args.resume)
        return

    elo_tracker = EloTracker(args.elo_db) if args.elo else None
    options = dict(
        delay=config["delay"],
        elo_tracker=elo_tracker,
        max_workers=config["max_workers"],
        openings_mode=config["openings_mode"],
        **config["player_kwargs"],
    )
    if args.round_robin:
        round_robin(args.round_robin, games_per_pair=args.games, **options)
    else:
        gauntlet(args.gauntlet, args.opponents, games_per_opponent=args.games, **options)


if __name__ == "__main__":
    main()
