from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from app.cache import state
from app.config import get_settings
from app.db import get_session
from app.models import MarketSnapshot, TickerUpdateEvent, TradeEvent
from app.strategy import implied_yes_ask, ranking_score, spread


def parse_ws_message(payload: dict[str, Any]) -> list[TickerUpdateEvent | TradeEvent]:
    message_type = payload.get("type")
    data = payload.get("data", payload)

    if message_type == "ticker":
        best_yes_bid = int(data.get("best_yes_bid") or data.get("yes_bid") or 0)
        best_no_bid = int(data.get("best_no_bid") or data.get("no_bid") or 0)
        top_yes_qty = int(data.get("top_yes_qty") or data.get("yes_bid_qty") or 0)
        top_no_qty = int(data.get("top_no_qty") or data.get("no_bid_qty") or 0)
        market_ticker = str(data.get("market_ticker") or data.get("ticker") or "")
        if not market_ticker:
            return []
        return [
            TickerUpdateEvent(
                market_ticker=market_ticker,
                best_yes_bid=best_yes_bid,
                best_no_bid=best_no_bid,
                top_yes_qty=top_yes_qty,
                top_no_qty=top_no_qty,
                raw=payload,
            )
        ]

    if message_type == "trade":
        market_ticker = str(data.get("market_ticker") or data.get("ticker") or "")
        if not market_ticker:
            return []
        return [
            TradeEvent(
                market_ticker=market_ticker,
                price=int(data.get("price") or 0),
                side=str(data.get("side") or "unknown"),
                quantity=int(data.get("quantity") or data.get("count") or 0),
                raw=payload,
            )
        ]

    return []


class KalshiWebSocketClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stop_event = asyncio.Event()

    @property
    def ws_url(self) -> str:
        return self.settings.kalshi_ws_url

    async def run_forever(self, tracked_tickers: list[str]) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._run_session(tracked_tickers)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                state.mark_disconnected()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _run_session(self, tracked_tickers: list[str]) -> None:
        if not tracked_tickers:
            await asyncio.sleep(1)
            return

        async with websockets.connect(self.ws_url) as websocket:
            state.mark_connected()
            await self._subscribe(websocket, tracked_tickers)
            async for raw_message in websocket:
                await self._handle_raw_message(raw_message)

    async def _subscribe(self, websocket: ClientConnection, tracked_tickers: list[str]) -> None:
        subscribe_payload = {
            "type": "subscribe",
            "channels": ["ticker", "trade"],
            "market_tickers": tracked_tickers,
        }
        await websocket.send(json.dumps(subscribe_payload))

    async def _handle_raw_message(self, raw_message: str) -> None:
        payload = json.loads(raw_message)
        for event in parse_ws_message(payload):
            if isinstance(event, TickerUpdateEvent):
                entry = state.apply_ticker_update(event)
                self._persist_ticker_entry(entry.market_ticker, event)
            elif isinstance(event, TradeEvent):
                state.apply_trade_update(event)

    def _persist_ticker_entry(self, market_ticker: str, event: TickerUpdateEvent) -> None:
        captured_at = datetime.now(timezone.utc)
        implied = implied_yes_ask(event.best_no_bid)
        spr = spread(event.best_yes_bid, implied)
        score = ranking_score(spr, event.top_yes_qty, event.top_no_qty, close_time=None)
        snapshot = MarketSnapshot(
            captured_at=captured_at,
            market_ticker=market_ticker,
            series_ticker=market_ticker.split("-")[0],
            close_time=None,
            best_yes_bid=event.best_yes_bid,
            best_no_bid=event.best_no_bid,
            implied_yes_ask=implied,
            spread=spr,
            top_yes_qty=event.top_yes_qty,
            top_no_qty=event.top_no_qty,
            score=score,
            raw_orderbook=json.dumps(event.raw),
        )
        with get_session() as session:
            session.add(snapshot)
            session.commit()

    def stop(self) -> None:
        self._stop_event.set()
