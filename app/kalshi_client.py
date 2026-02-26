from __future__ import annotations

from datetime import datetime

import httpx

from app.config import get_settings
from app.models import KalshiMarket, KalshiOrderbook


class KalshiClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.kalshi_base_url
        self.timeout = timeout or settings.request_timeout_seconds

    async def get_markets(
        self,
        series_ticker: str,
        status: str = "open",
        cursor: str | None = None,
    ) -> tuple[list[KalshiMarket], str | None]:
        params = {"series_ticker": series_ticker, "status": status}
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/markets", params=params)
            response.raise_for_status()

        payload = response.json()
        markets: list[KalshiMarket] = []
        for item in payload.get("markets", []):
            close_ts = item.get("close_time")
            close_time = datetime.fromisoformat(close_ts.replace("Z", "+00:00")) if close_ts else None
            markets.append(
                KalshiMarket(
                    ticker=item["ticker"],
                    series_ticker=item.get("series_ticker", series_ticker),
                    close_time=close_time,
                )
            )
        return markets, payload.get("cursor")

    async def get_orderbook(self, market_ticker: str) -> KalshiOrderbook:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get(f"/markets/{market_ticker}/orderbook")
            response.raise_for_status()

        payload = response.json()
        orderbook = payload.get("orderbook", payload)
        return KalshiOrderbook(
            market_ticker=market_ticker,
            yes=orderbook.get("yes", []),
            no=orderbook.get("no", []),
            raw=payload,
        )
