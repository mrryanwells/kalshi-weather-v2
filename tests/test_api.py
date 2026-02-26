from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app, scanner, settings


def test_api_opportunities_filter_and_sort_params() -> None:
    sample = [
        {
            "market_ticker": "KXHIGHNY-1",
            "series_ticker": "KXHIGHNY",
            "best_yes_bid": 45,
            "implied_yes_ask": 55,
            "implied_no_ask": 55,
            "spread": 10,
            "top_yes_qty": 150,
            "top_no_qty": 140,
            "score": 0.7,
            "last_update_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "age_seconds": 4,
            "reason": "demo",
            "actionable": True,
        }
    ]

    captured: dict = {}
    original_rows = scanner.latest_market_rows
    original_ws_enabled = settings.websocket_enabled

    def fake_rows(**kwargs):
        captured.update(kwargs)
        return sample

    scanner.latest_market_rows = fake_rows  # type: ignore[assignment]

    try:
        settings.websocket_enabled = False
        client = TestClient(app)
        response = client.get(
            "/api/opportunities",
            params={
                "series_ticker": "KXHIGHNY",
                "max_spread": 3,
                "min_yes_qty": 50,
                "min_no_qty": 50,
                "min_score": 0.5,
                "price_min": 15,
                "price_max": 85,
                "actionable_only": "true",
                "sort_by": "depth_desc",
            },
        )
    finally:
        scanner.latest_market_rows = original_rows
        settings.websocket_enabled = original_ws_enabled

    assert response.status_code == 200
    assert response.json()[0]["market_ticker"] == "KXHIGHNY-1"
    assert captured["series_ticker"] == "KXHIGHNY"
    assert captured["max_spread"] == 3
    assert captured["min_yes_qty"] == 50
    assert captured["min_no_qty"] == 50
    assert captured["sort_by"] == "depth_desc"
    assert captured["actionable_only"] is True


def test_dashboard_route_smoke() -> None:
    original_rows = scanner.latest_market_rows
    original_ws_enabled = settings.websocket_enabled
    scanner.latest_market_rows = lambda **kwargs: []  # type: ignore[assignment]

    try:
        settings.websocket_enabled = False
        client = TestClient(app)
        response = client.get("/")
    finally:
        scanner.latest_market_rows = original_rows
        settings.websocket_enabled = original_ws_enabled

    assert response.status_code == 200
    assert "Kalshi Trading Console" in response.text
    assert "max_spread" in response.text
