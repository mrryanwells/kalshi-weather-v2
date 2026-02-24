from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from app.db import get_session
from app.models import MarketSnapshot, PaperFill, PaperOrder
from app.paper_engine import PaperOrderCreate, PaperTradingEngine, position_lifecycle, simulate_fill


def _reset_tables() -> None:
    with get_session() as session:
        session.exec(PaperFill.__table__.delete())
        session.exec(PaperOrder.__table__.delete())
        session.exec(MarketSnapshot.__table__.delete())
        session.commit()


def _seed_snapshot() -> None:
    with get_session() as session:
        session.add(
            MarketSnapshot(
                captured_at=datetime.now(timezone.utc),
                market_ticker="KXHIGHNY-24DEC31-B35",
                series_ticker="KXHIGHNY",
                close_time=None,
                best_yes_bid=46,
                best_no_bid=52,
                implied_yes_ask=48,
                spread=2,
                top_yes_qty=80,
                top_no_qty=60,
                score=0.5,
                raw_orderbook="{}",
            )
        )
        session.commit()


def test_fill_simulation_buy_yes_crosses_limit() -> None:
    _reset_tables()
    _seed_snapshot()
    with get_session() as session:
        snapshot = session.exec(select(MarketSnapshot)).first()
    assert snapshot is not None
    order = PaperOrder(
        created_at=datetime.now(timezone.utc),
        market_ticker="KXHIGHNY-24DEC31-B35",
        side="yes",
        action="buy",
        limit_price=49,
        quantity=100,
        filled_quantity=0,
        status="open",
    )
    decision = simulate_fill(order, snapshot, 0)
    assert decision.should_fill is True
    assert decision.fill_price == 48
    assert decision.fill_qty == 60


def test_position_lifecycle_realized_pl() -> None:
    fills = [
        PaperFill(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), order_id=1, market_ticker="M", side="yes", action="buy", price=40, quantity=10),
        PaperFill(created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), order_id=2, market_ticker="M", side="yes", action="sell", price=55, quantity=4),
    ]
    qty, avg_cost, realized = position_lifecycle(fills)
    assert qty == 6
    assert round(avg_cost, 2) == 40.00
    assert round(realized, 2) == 60.00


def test_position_lifecycle_round_trip_closed() -> None:
    fills = [
        PaperFill(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), order_id=1, market_ticker="M", side="yes", action="buy", price=50, quantity=5),
        PaperFill(created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), order_id=2, market_ticker="M", side="yes", action="sell", price=60, quantity=5),
    ]
    qty, avg_cost, realized = position_lifecycle(fills)
    assert qty == 0
    assert avg_cost == 0
    assert realized == 50


def test_engine_places_order_and_creates_fill() -> None:
    _reset_tables()
    _seed_snapshot()
    engine = PaperTradingEngine()
    order = engine.place_order(
        PaperOrderCreate(
            market_ticker="KXHIGHNY-24DEC31-B35",
            side="yes",
            action="buy",
            limit_price=49,
            quantity=20,
            notes="test",
        )
    )
    assert order.filled_quantity == 20
    fills = engine.list_fills()
    assert len(fills) == 1
