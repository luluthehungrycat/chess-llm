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
import threading
import time
from itertools import count
from pathlib import Path
from typing import Optional

# Add parent to path so we can import chess_llm modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elo import EloTracker, player_id
from chess_llm import ChessMatch


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


def parse_player_spec(spec: str):
    """Parse a player spec and build the player.

    Returns (player_type, player, elo_id, overrides). Parsing is delegated to
    chess_llm.parse_player, so @presets, ?flags and stockfish:N behave exactly
    as in single games; unknown presets raise ValueError. ``overrides`` are
    the per-model LLM kwargs (models.yaml defaults + preset + inline flags)
    that win over global tournament flags.
    """
    from chess_llm import (HumanPlayer, LLMPlayer, LLM_PLAYER_KWARGS, RandomPlayer,
                           StockfishPlayer, parse_player)

    ptype, kwargs = parse_player(spec)
    elo_id = player_id(spec)
    if ptype == "human":
        return ptype, HumanPlayer(name=kwargs["name"]), elo_id, {}
    if ptype == "random":
        return ptype, RandomPlayer(name="Random"), elo_id, {}
    if ptype == "stockfish":
        player = StockfishPlayer(name=kwargs["name"], skill_level=kwargs["skill"])
        return ptype, player, elo_id, {}
    overrides = {k: v for k, v in kwargs.items() if k in LLM_PLAYER_KWARGS}
    return ptype, LLMPlayer(**kwargs), elo_id, overrides


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
    _, white, w_id, white_overrides = parse_player_spec(white_spec)
    _, black, b_id, black_overrides = parse_player_spec(black_spec)

    # Merge: model_config defaults → preset → inline query → CLI kwargs
    # Per-model overrides from config/query take priority over global CLI flags
    for p, overrides in ((white, white_overrides), (black, black_overrides)):
        for k, v in player_kwargs.items():
            # Only set if we have a setter (skip if the override already covers it)
            if hasattr(p, k) and k not in overrides:
                if k == "timeout" and hasattr(p, "model") and getattr(p, "model", "").startswith("bigpickle/") and v == 120:
                    v = 240
                setattr(p, k, v)
        # Now apply per-model overrides (these win over global flags)
        for k, v in overrides.items():
            if hasattr(p, k):
                setattr(p, k, v)

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


def round_robin(models: list[str], games_per_pair: int = 1,
                delay: float = 0.5, elo_tracker: Optional[EloTracker] = None,
                max_workers: int = 1, openings_mode: str = "standard",
                **player_kwargs):
    """Run a round-robin tournament (each model plays every other as both colors).

    When max_workers > 1, games run in parallel via ThreadPoolExecutor.
    ELO updates are batched after all games complete to avoid file corruption.
    openings_mode: 'standard' (default) or 'unbalanced' (forces decisive games).
    """
    total_games = len(models) * (len(models) - 1) * games_per_pair
    print(f"\n🏟  Round-Robin Tournament: {len(models)} players")
    print(f"   Models: {', '.join(models)}")
    print(f"   Games per pair: {games_per_pair}")
    print(f"   Total games: {total_games}")
    if openings_mode == "unbalanced":
        from openings import OPENINGS
        print(f"   Openings: unbalanced ({len(OPENINGS)} lines, alternating advantage)")
    if max_workers > 1:
        print(f"   Parallel workers: {max_workers}  |  ELO: batch-at-end")

    # Lazy-load openings module
    _openings_uci = None

    def _get_starting_board(opening_idx: int):
        """Return (board, opening_name) for the given opening index, or (None, '')."""
        nonlocal _openings_uci
        if openings_mode != "unbalanced":
            return None, ""
        if _openings_uci is None:
            from openings import OPENINGS
            _openings_uci = OPENINGS
        import chess
        name, moves, advantage = _openings_uci[opening_idx % len(_openings_uci)]
        board = chess.Board()
        for uci in moves:
            board.push_uci(uci)
        return board, name

    results = []
    start_time = time.time()

    # ── Build task list ───────────────────────────────────────────────
    tasks = []
    opening_counter = 0
    for i, white_model in enumerate(models):
        for j, black_model in enumerate(models):
            if i == j:
                continue
            for g in range(games_per_pair):
                tasks.append((white_model, black_model, g, opening_counter))
                opening_counter += 1

    # ── Sequential mode ───────────────────────────────────────────────
    if max_workers <= 1:
        for white_model, black_model, g, oi in tasks:
            board, oname = _get_starting_board(oi)
            print(f"\n── Round: {white_model} vs {black_model} "
                  f"(game {g + 1}/{games_per_pair}) ──")
            try:
                result = run_match(
                    white_model, black_model,
                    delay=delay, elo_tracker=elo_tracker,
                    starting_board=board, opening_name=oname,
                    **player_kwargs,
                )
                results.append((white_model, black_model, result))
            except Exception as e:
                print(f"  ❌ Match failed: {e}")
                results.append((white_model, black_model, "error"))
            time.sleep(0.5)

    # ── Parallel mode ─────────────────────────────────────────────────
    else:
        completed = 0
        failed = 0
        _lock = threading.Lock()

        def _run_one(task):
            white_model, black_model, g, oi = task
            board, oname = _get_starting_board(oi)
            try:
                result = run_match(
                    white_model, black_model,
                    delay=delay, elo_tracker=None,
                    starting_board=board, opening_name=oname,
                    **player_kwargs,
                )
                return (white_model, black_model, result, None)
            except Exception as e:
                return (white_model, black_model, "error", str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                white_model, black_model, result, error = future.result()
                with _lock:
                    completed += 1
                    if error:
                        failed += 1
                    results.append((white_model, black_model, result))
                    pct = completed * 100 // len(tasks)
                    status = f"  ⚡ [{completed}/{len(tasks)}] {pct}%  "
                    if failed:
                        status += f"({failed} failed)  "
                    status += f"{white_model} vs {black_model} → {result}"
                    print(status)

        # ── Batch ELO update ──────────────────────────────────────────
        if elo_tracker:
            print(f"\n📊 Computing ELO ratings...")
            for white_model, black_model, result in results:
                if result == "error":
                    continue
                w_id = _elo_id_from_spec(white_model)
                b_id = _elo_id_from_spec(black_model)
                elo_tracker.update(w_id, b_id, result)
            elo_tracker.print_leaderboard()
            return results

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"  Tournament complete in {elapsed:.0f}s")
    print(f"  Games: {len(results)}")
    if elo_tracker and max_workers <= 1:
        elo_tracker.print_leaderboard()
    return results


def gauntlet(champion: str, opponents: list[str],
             games_per_opponent: int = 1, delay: float = 0.5,
             elo_tracker: Optional[EloTracker] = None,
             max_workers: int = 1, **player_kwargs):
    """Gauntlet: champion plays each opponent (both colors).

    When max_workers > 1, games run in parallel via ThreadPoolExecutor.
    ELO updates are batched after all games complete.
    """
    total_games = len(opponents) * games_per_opponent * 2
    print(f"\n🏟  Gauntlet: {champion} vs the field")
    print(f"   Opponents: {', '.join(opponents)}")
    print(f"   Games per opponent: {games_per_opponent * 2} (both colors)")
    if max_workers > 1:
        print(f"   Parallel workers: {max_workers}  |  ELO: batch-at-end")

    results = []
    start_time = time.time()

    # ── Build task list ───────────────────────────────────────────────
    tasks = []
    for opponent in opponents:
        for g in range(games_per_opponent):
            tasks.append((champion, opponent, g, "W"))   # champion as white
            tasks.append((opponent, champion, g, "B"))   # champion as black

    # ── Sequential mode ───────────────────────────────────────────────
    if max_workers <= 1:
        for white_model, black_model, g, _ in tasks:
            print(f"\n── Gauntlet: {white_model} (W) vs {black_model} (B) "
                  f"(game {g + 1}) ──")
            try:
                result = run_match(white_model, black_model, delay=delay,
                                   elo_tracker=elo_tracker, **player_kwargs)
                results.append((white_model, black_model, result))
            except Exception as e:
                print(f"  ❌ Match failed: {e}")
                results.append((white_model, black_model, "error"))

    # ── Parallel mode ─────────────────────────────────────────────────
    else:
        completed = 0
        failed = 0
        _lock = threading.Lock()

        def _run_one(task):
            white_model, black_model, g, _ = task
            try:
                result = run_match(
                    white_model, black_model,
                    delay=delay, elo_tracker=None,
                    **player_kwargs,
                )
                return (white_model, black_model, result, None)
            except Exception as e:
                return (white_model, black_model, "error", str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                white_model, black_model, result, error = future.result()
                with _lock:
                    completed += 1
                    if error:
                        failed += 1
                    results.append((white_model, black_model, result))
                    pct = completed * 100 // len(tasks)
                    status = f"  ⚡ [{completed}/{len(tasks)}] {pct}%  "
                    if failed:
                        status += f"({failed} failed)  "
                    status += f"{white_model} vs {black_model} → {result}"
                    print(status)

        # ── Batch ELO update ──────────────────────────────────────────
        if elo_tracker:
            print(f"\n📊 Computing ELO ratings...")
            for white_model, black_model, result in results:
                if result == "error":
                    continue
                w_id = _elo_id_from_spec(white_model)
                b_id = _elo_id_from_spec(black_model)
                elo_tracker.update(w_id, b_id, result)
            elo_tracker.print_leaderboard()
            return results

    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"  Gauntlet complete in {elapsed:.0f}s")
    if elo_tracker and max_workers <= 1:
        elo_tracker.print_leaderboard()
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

    mode = parser.add_mutually_exclusive_group(required=True)
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
    parser.add_argument("--no-tools", action="store_true",
                        help="Disable tool calling for LLM players")
    parser.add_argument("--tiny", action="store_true",
                        help="Tiny-model mode: compact UCI-only prompt for models <20B. "
                             "Forces --no-tools, strips FEN, uses strict MOVE: <uci> format.")
    parser.add_argument("--constrain", action="store_true",
                        help="Force legal moves: when the model proposes an illegal move, "
                             "pick the closest legal move instead of retrying or forfeiting.")
    parser.add_argument("--reasoning", choices=["low", "medium", "high", "none"],
                        default=None,
                        help="Reasoning effort for providers that support it "
                             "(OpenRouter/OpenAI: reasoning_effort; Anthropic: thinking budget). "
                             "Use \"none\" to skip reasoning. Omit for provider default.")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--model-flags", type=str, default=None,
                        help="Comma-separated key=val flags applied to ALL LLM players "
                             "(e.g. tools=off,tiny=true,retries=10). "
                             "Per-model config from models.yaml takes priority.")
    parser.add_argument("--stockfish-skill", type=int, default=20)
    parser.add_argument("--stockfish-time", type=float, default=0.1)
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
    parser.add_argument("--resume", action="store_true",
                        help="Resume a saved tournament from tournament_state.json")
    parser.add_argument("--log", "-l", nargs="?", const="auto", default=None,
                        help="Tee output to a log file (auto-names by date; or give a path)")

    args = parser.parse_args()

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

    # ── TUI path ──────────────────────────────────────────────────────
    if use_tui:
        try:
            from tui.tournament import TournamentApp
            from tui.state import load_state

            # Resume from saved state
            resume_completed = None
            resume_elo = None

            if args.resume:
                state = load_state()
                if state is None:
                    print("❌ No saved tournament state found (tournament_state.json missing)")
                    sys.exit(1)
                cfg = state["config"]
                models = cfg["models"]
                games_per_pair = cfg["games_per_pair"]
                delay = cfg["delay"]
                workers = cfg["max_workers"]
                player_kwargs = cfg["player_kwargs"]
                elo_db = cfg.get("elo_db_path")
                resume_completed = [tuple(r) for r in state["completed"]]
                resume_elo = state.get("elo_ratings", {})
                print(f"📂 Resuming tournament: {len(resume_completed)} games already completed, "
                      f"{len(models)} players")
            else:
                models = args.round_robin if args.round_robin else (
                    [args.gauntlet] + (args.opponents or [])
                )
                games_per_pair = args.games
                delay = args.delay
                workers = max(args.parallel, 1)
                player_kwargs = dict(
                    use_tools=not args.no_tools,
                    max_retries=args.retries,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    threads=args.stockfish_threads,
                    think_time=args.stockfish_time,
                    tiny=args.tiny,
                    reasoning=args.reasoning,
                    constrain=args.constrain,
                )
                # Merge --model-flags (applied to all models, but per-model config wins)
                if args.model_flags:
                    from model_config import _parse_query_flags
                    player_kwargs.update(_parse_query_flags(args.model_flags))
                elo_db = args.elo_db if args.elo else None

            app = TournamentApp(
                models=models,
                games_per_pair=games_per_pair,
                delay=delay,
                elo_db_path=elo_db,
                player_kwargs=player_kwargs,
                max_workers=workers,
                resume_completed=resume_completed,
                resume_elo=resume_elo,
                openings_mode=args.openings if not args.resume else resume_elo.get("openings_mode", "standard"),
            )
            app.run()
            return
        except Exception as e:
            if args.tui:
                # Explicit --tui: the user asked for the dashboard, so show the
                # real error instead of quietly running something else.
                raise
            print(f"⚠ TUI failed to start: {e}", file=sys.stderr)
            print("Falling back to plain-text mode. Use --no-tui to skip this warning.", file=sys.stderr)
            # Fall through to non-TUI path below

    # ELO tracker
    elo_tracker = EloTracker(args.elo_db) if args.elo else None

    player_kwargs = dict(
        use_tools=not args.no_tools,
        max_retries=args.retries,
        temperature=args.temperature,
        timeout=args.timeout,
        threads=args.stockfish_threads,
        think_time=args.stockfish_time,
        tiny=args.tiny,
        reasoning=args.reasoning,
        constrain=args.constrain,
    )
    # Merge --model-flags (applied to all models, but per-model config wins)
    if args.model_flags:
        from model_config import _parse_query_flags
        player_kwargs.update(_parse_query_flags(args.model_flags))

    if args.round_robin:
        round_robin(
            args.round_robin,
            games_per_pair=args.games,
            delay=args.delay,
            elo_tracker=elo_tracker,
            max_workers=args.parallel,
            openings_mode=args.openings,
            **player_kwargs,
        )
    elif args.gauntlet:
        if not args.opponents:
            print("❌ --gauntlet requires --opponents")
            sys.exit(1)
        gauntlet(
            args.gauntlet,
            args.opponents,
            games_per_opponent=args.games,
            delay=args.delay,
            elo_tracker=elo_tracker,
            max_workers=args.parallel,
            **player_kwargs,
        )


if __name__ == "__main__":
    main()
