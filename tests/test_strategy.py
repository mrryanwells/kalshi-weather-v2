from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.strategy import implied_yes_ask, ranking_score, spread


def test_implied_yes_ask_and_spread_math() -> None:
    best_no_bid = 58
    yes_ask = implied_yes_ask(best_no_bid)
    assert yes_ask == 42

    best_yes_bid = 39
    assert spread(best_yes_bid, yes_ask) == 3


def test_ranking_score_prefers_tighter_and_deeper_markets() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close_time = now + timedelta(hours=1)

    tight_deep = ranking_score(2, 400, 450, close_time, now=now)
    wide_shallow = ranking_score(10, 40, 50, close_time, now=now)

    assert tight_deep > wide_shallow
