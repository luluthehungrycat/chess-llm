"""ELO leaderboard + matchup summary rendering helpers.

Pure functions, no Textual dependency. Easy to unit-test.
"""

from typing import Optional


def render_leaderboard_rows(elo_tracker, n: int = 20) -> list[tuple[str, str, str, str, str, str, str]]:
    """Return leaderboard rows for the ELO DataTable.

    Each row: (rank, player, rating, games, wins, losses, draws) — all
    pre-formatted as strings.
    """
    board = elo_tracker.leaderboard(n=n)
    rows = []
    for i, (pid, stats) in enumerate(board, 1):
        rows.append((
            str(i),
            pid,
            str(stats["rating"]),
            str(stats["games"]),
            str(stats.get("wins", 0)),
            str(stats.get("losses", 0)),
            str(stats.get("draws", 0)),
        ))
    return rows


def render_matchup_summary(
    completed: list[tuple[str, str, str]],
    elo_tracker,
    game_durations: dict[str, list[float]],
    top_n: int = 10,
) -> str:
    """Return a multi-line string of W-D-L per player, sorted by ELO.

    Each line: `short_name  W-D-L  ~X.Xs/game` (timing omitted if no data).
    """
    if not completed:
        return ""

    summary: dict[str, dict[str, int]] = {}
    for wm, bm, result in completed:
        from .runner import _elo_id
        wid = _elo_id(wm)
        bid = _elo_id(bm)
        for pid in (wid, bid):
            summary.setdefault(pid, {"W": 0, "D": 0, "L": 0})
        if result == "1-0":
            summary[wid]["W"] += 1
            summary[bid]["L"] += 1
        elif result == "0-1":
            summary[wid]["L"] += 1
            summary[bid]["W"] += 1
        else:
            summary[wid]["D"] += 1
            summary[bid]["D"] += 1

    lines = ["  📊  Results:  W–D–L"]
    board = elo_tracker.leaderboard()
    for pid, _ in board[:top_n]:
        if pid not in summary:
            continue
        s = summary[pid]
        short = pid if len(pid) <= 16 else pid[:13] + "..."
        avg_time = ""
        if pid in game_durations and game_durations[pid]:
            avg = sum(game_durations[pid]) / len(game_durations[pid])
            avg_time = f"  ~{avg:.0f}s/game"
        lines.append(f"    {short:<17} {s['W']}–{s['D']}–{s['L']}{avg_time}")
    return "\n".join(lines)
