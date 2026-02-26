from __future__ import annotations

from datetime import datetime, timezone


def implied_yes_ask(best_no_bid: int) -> int:
    return 100 - best_no_bid


def spread(best_yes_bid: int, implied_yes_ask_value: int) -> int:
    return implied_yes_ask_value - best_yes_bid


def ranking_score(
    spread_value: int,
    top_yes_qty: int,
    top_no_qty: int,
    close_time: datetime | None,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    depth = min(top_yes_qty, top_no_qty)

    if close_time is None:
        time_bonus = 0.0
    else:
        seconds_to_close = max(0.0, (close_time - now).total_seconds())
        hours_to_close = seconds_to_close / 3600
        time_bonus = 1 / (1 + hours_to_close)

    tightness = 1 / (1 + max(0, spread_value))
    depth_component = min(depth / 500, 1.0)
    return round(0.6 * tightness + 0.25 * depth_component + 0.15 * time_bonus, 6)
