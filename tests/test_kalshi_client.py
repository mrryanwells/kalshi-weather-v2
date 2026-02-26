from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from app.kalshi_client import KalshiClient

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_get_markets_mocked_response() -> None:
    payload = json.loads((FIXTURE_DIR / "markets_response.json").read_text())
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as mock:
        mock.get("/markets").respond(200, json=payload)
        client = KalshiClient()
        markets, cursor = await client.get_markets(series_ticker="KXHIGHNY")

    assert len(markets) == 1
    assert markets[0].ticker == "KXHIGHNY-24DEC31-B35"
    assert cursor is None


@pytest.mark.asyncio
async def test_get_orderbook_mocked_response() -> None:
    payload = json.loads((FIXTURE_DIR / "orderbook_response.json").read_text())
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as mock:
        mock.get("/markets/KXHIGHNY-24DEC31-B35/orderbook").respond(200, json=payload)
        client = KalshiClient()
        orderbook = await client.get_orderbook("KXHIGHNY-24DEC31-B35")

    assert orderbook.yes[0] == [47, 120]
    assert orderbook.no[0] == [52, 150]
