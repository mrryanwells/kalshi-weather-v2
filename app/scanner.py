from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

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

    def latest_market_rows(
        self,
        *,
        series_ticker: str | None = None,
        max_spread: int | None = None,
        min_depth: int | None = None,
        min_yes_qty: int | None = None,
        min_no_qty: int | None = None,
        min_score: float | None = None,
        price_min: int | None = None,
        price_max: int | None = None,
        actionable_only: bool = False,
        sort_by: str = "score_desc",
        limit: int = 200,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        with get_session() as session:
            ordered = session.exec(
                select(MarketSnapshot).order_by(desc(MarketSnapshot.captured_at), desc(MarketSnapshot.id)).limit(limit * 20)
            ).all()

        latest_by_market: dict[str, MarketSnapshot] = {}
        for row in ordered:
            if row.market_ticker not in latest_by_market:
                latest_by_market[row.market_ticker] = row

        rows: list[dict[str, Any]] = []
        for row in latest_by_market.values():
            implied_no_ask = 100 - row.best_yes_bid
            age_seconds = max(0, int((current - row.captured_at).total_seconds()))
            actionable = self._is_actionable(
                row,
                max_spread=max_spread,
                min_yes_qty=min_yes_qty,
                min_no_qty=min_no_qty,
                min_score=min_score,
                price_min=price_min,
                price_max=price_max,
            )
            rows.append(
                {
                    "market_ticker": row.market_ticker,
                    "series_ticker": row.series_ticker,
                    "best_yes_bid": row.best_yes_bid,
                    "implied_yes_ask": row.implied_yes_ask,
                    "implied_no_ask": implied_no_ask,
                    "spread": row.spread,
                    "top_yes_qty": row.top_yes_qty,
                    "top_no_qty": row.top_no_qty,
                    "score": row.score,
                    "last_update_time": row.captured_at,
                    "close_time": row.close_time,
                    "age_seconds": age_seconds,
                    "reason": self._score_reason(row),
                    "actionable": actionable,
                }
            )

        if series_ticker:
            rows = [r for r in rows if r["series_ticker"] == series_ticker]
        if max_spread is not None:
            rows = [r for r in rows if r["spread"] <= max_spread]
        if min_depth is not None:
            rows = [r for r in rows if min(r["top_yes_qty"], r["top_no_qty"]) >= min_depth]
        if min_yes_qty is not None:
            rows = [r for r in rows if r["top_yes_qty"] >= min_yes_qty]
        if min_no_qty is not None:
            rows = [r for r in rows if r["top_no_qty"] >= min_no_qty]
        if min_score is not None:
            rows = [r for r in rows if r["score"] >= min_score]
        if price_min is not None:
            rows = [r for r in rows if r["best_yes_bid"] >= price_min]
        if price_max is not None:
            rows = [r for r in rows if r["best_yes_bid"] <= price_max]
        if actionable_only:
            rows = [r for r in rows if r["actionable"]]

        self._sort_rows(rows, sort_by)
        return rows[:limit]

    @staticmethod
    def _sort_rows(rows: list[dict[str, Any]], sort_by: str) -> None:
        if sort_by == "spread_asc":
            rows.sort(key=lambda x: (x["spread"], -x["score"]))
        elif sort_by == "depth_desc":
            rows.sort(key=lambda x: (min(x["top_yes_qty"], x["top_no_qty"]), x["score"]), reverse=True)
        elif sort_by == "close_soon":
            rows.sort(key=lambda x: (x["close_time"] is None, x["close_time"] or datetime.max.replace(tzinfo=timezone.utc)))
        else:  # score_desc default
            rows.sort(key=lambda x: x["score"], reverse=True)

    @staticmethod
    def _score_reason(row: MarketSnapshot) -> str:
        depth = min(row.top_yes_qty, row.top_no_qty)
        if row.spread <= 2 and depth >= 100 and row.score >= 0.6:
            return "Tight spread + strong depth"
        if row.spread <= 4 and row.score >= 0.45:
            return "Tradable spread, moderate edge"
        if depth < 50:
            return "Low depth limits fill quality"
        return "Watchlist candidate"

    @staticmethod
    def _is_actionable(
        row: MarketSnapshot,
        *,
        max_spread: int | None,
        min_yes_qty: int | None,
        min_no_qty: int | None,
        min_score: float | None,
        price_min: int | None,
        price_max: int | None,
    ) -> bool:
        spread_ok = row.spread <= (max_spread if max_spread is not None else 3)
        yes_ok = row.top_yes_qty >= (min_yes_qty if min_yes_qty is not None else 50)
        no_ok = row.top_no_qty >= (min_no_qty if min_no_qty is not None else 50)
        score_ok = row.score >= (min_score if min_score is not None else 0.2)
        pmin = price_min if price_min is not None else 15
        pmax = price_max if price_max is not None else 85
        price_ok = pmin <= row.best_yes_bid <= pmax
        return spread_ok and yes_ok and no_ok and score_ok and price_ok

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
