from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app, settings
from app.db import get_session
from app.models import MarketSnapshot, PaperFill, PaperOrder


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


def test_paper_order_routes() -> None:
    _reset_tables()
    _seed_snapshot()
    original = settings.websocket_enabled
    settings.websocket_enabled = False
    try:
        client = TestClient(app)
        resp = client.post(
            "/paper/orders",
            data={
                "market_ticker": "KXHIGHNY-24DEC31-B35",
                "side": "yes",
                "action": "buy",
                "limit_price": 49,
                "quantity": 10,
                "notes": "route-test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        api_orders = client.get("/api/paper/orders")
        assert api_orders.status_code == 200
        assert len(api_orders.json()) >= 1

        api_positions = client.get("/api/paper/positions")
        assert api_positions.status_code == 200

        csv_resp = client.get("/api/paper/trades.csv")
        assert csv_resp.status_code == 200
        assert "market_ticker" in csv_resp.text
    finally:
        settings.websocket_enabled = original
