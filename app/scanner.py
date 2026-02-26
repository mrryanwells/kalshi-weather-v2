from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import desc, select

from app.config import get_settings
from app.db import get_session
from app.kalshi_client import KalshiClient
from app.models import MarketSnapshot, Opportunity
from app.strategy import implied_yes_ask, ranking_score, spread


class ScannerService:
    def __init__(self, client: KalshiClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or KalshiClient()

    async def scan_once(self) -> list[MarketSnapshot]:
        captured_at = datetime.now(timezone.utc)
        snapshots: list[MarketSnapshot] = []

        for series in self.settings.series_tickers:
            cursor: str | None = None
            while True:
                markets, cursor = await self.client.get_markets(series_ticker=series, status="open", cursor=cursor)
                for market in markets:
                    orderbook = await self.client.get_orderbook(market.ticker)
                    best_yes_bid, top_yes_qty = self._top_level(orderbook.yes)
                    best_no_bid, top_no_qty = self._top_level(orderbook.no)
                    implied = implied_yes_ask(best_no_bid)
                    spr = spread(best_yes_bid, implied)
                    score = ranking_score(spr, top_yes_qty, top_no_qty, market.close_time)

                    snapshots.append(
                        MarketSnapshot(
                            captured_at=captured_at,
                            market_ticker=market.ticker,
                            series_ticker=market.series_ticker,
                            close_time=market.close_time,
                            best_yes_bid=best_yes_bid,
                            best_no_bid=best_no_bid,
                            implied_yes_ask=implied,
                            spread=spr,
                            top_yes_qty=top_yes_qty,
                            top_no_qty=top_no_qty,
                            score=score,
                            raw_orderbook=json.dumps(orderbook.raw),
                        )
                    )
                if not cursor:
                    break

        if snapshots:
            with get_session() as session:
                session.add_all(snapshots)
                session.commit()

        return snapshots


    async def tracked_market_tickers(self) -> list[str]:
        tickers: list[str] = []
        for series in self.settings.series_tickers:
            cursor: str | None = None
            while True:
                markets, cursor = await self.client.get_markets(series_ticker=series, status="open", cursor=cursor)
                tickers.extend([market.ticker for market in markets])
                if not cursor:
                    break
        return sorted(set(tickers))

    def latest_opportunities(self, limit: int = 50) -> list[Opportunity]:
        with get_session() as session:
            rows = session.exec(
                select(MarketSnapshot).order_by(desc(MarketSnapshot.captured_at), desc(MarketSnapshot.score)).limit(limit)
            ).all()

        return [Opportunity.model_validate(row.model_dump()) for row in rows]

    def get_market_history(self, ticker: str, limit: int = 100) -> list[MarketSnapshot]:
        with get_session() as session:
            return session.exec(
                select(MarketSnapshot)
                .where(MarketSnapshot.market_ticker == ticker)
                .order_by(desc(MarketSnapshot.captured_at))
                .limit(limit)
            ).all()

    @staticmethod
    def _top_level(side_levels: list[list[int]]) -> tuple[int, int]:
        if not side_levels:
            return 0, 0
        first = side_levels[0]
        price = int(first[0]) if len(first) >= 1 else 0
        qty = int(first[1]) if len(first) >= 2 else 0
        return price, qty
