from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app, scanner, settings
from app.models import Opportunity


def test_api_opportunities_route() -> None:
    sample = Opportunity(
        market_ticker="KXHIGHNY-24DEC31-B35",
        series_ticker="KXHIGHNY",
        close_time=datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc),
        best_yes_bid=47,
        best_no_bid=52,
        implied_yes_ask=48,
        spread=1,
        top_yes_qty=120,
        top_no_qty=150,
        score=0.77,
    )

    original = scanner.latest_opportunities
    original_ws_enabled = settings.websocket_enabled
    scanner.latest_opportunities = lambda limit=100: [sample]

    try:
        settings.websocket_enabled = False
        client = TestClient(app)
        response = client.get("/api/opportunities")
    finally:
        scanner.latest_opportunities = original
        settings.websocket_enabled = original_ws_enabled

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["market_ticker"] == "KXHIGHNY-24DEC31-B35"
    assert payload[0]["spread"] == 1
