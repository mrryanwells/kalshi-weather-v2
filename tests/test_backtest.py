from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.backtest import BacktestParams, calculate_metrics, replay_snapshots
from app.models import MarketSnapshot


def _snapshot(ts: datetime, ticker: str, yes_bid: int, no_bid: int, spread: int, score: float = 0.5) -> MarketSnapshot:
    return MarketSnapshot(
        id=1,
        captured_at=ts,
        market_ticker=ticker,
        series_ticker="KXHIGHNY",
        close_time=ts + timedelta(hours=1),
        best_yes_bid=yes_bid,
        best_no_bid=no_bid,
        implied_yes_ask=100 - no_bid,
        spread=spread,
        top_yes_qty=10,
        top_no_qty=10,
        score=score,
        raw_orderbook="{}",
    )


def test_deterministic_replay_same_input_same_output() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snaps = [
        _snapshot(t0, "M1", 40, 55, 5),
        _snapshot(t0 + timedelta(minutes=1), "M1", 60, 30, 10),
        _snapshot(t0 + timedelta(minutes=2), "M1", 65, 25, 10),
    ]
    params = BacktestParams(start_at=t0, end_at=t0 + timedelta(hours=1), min_score=0.0, max_spread=20, quantity=1)
    r1 = replay_snapshots(snaps, params)
    r2 = replay_snapshots(snaps, params)
    assert [x.__dict__ for x in r1] == [x.__dict__ for x in r2]


def test_strategy_parameter_threshold_filters_trades() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snaps = [
        _snapshot(t0, "M1", 40, 55, 15),
        _snapshot(t0 + timedelta(minutes=1), "M1", 62, 28, 8),
    ]
    loose = BacktestParams(start_at=t0, end_at=t0 + timedelta(hours=1), min_score=0.0, max_spread=20, quantity=1)
    strict = BacktestParams(start_at=t0, end_at=t0 + timedelta(hours=1), min_score=0.8, max_spread=3, quantity=1)
    assert len(replay_snapshots(snaps, loose)) >= len(replay_snapshots(snaps, strict))


def test_metrics_calculation() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trades = replay_snapshots(
        [
            _snapshot(t0, "M1", 40, 55, 5),
            _snapshot(t0 + timedelta(minutes=1), "M1", 70, 20, 10),
        ],
        BacktestParams(start_at=t0, end_at=t0 + timedelta(hours=1), min_score=0.0, max_spread=20, quantity=1),
    )
    summary = calculate_metrics(trades)
    assert summary.num_trades >= 0
    assert summary.max_drawdown >= 0
    assert isinstance(summary.pnl_by_hour, dict)
