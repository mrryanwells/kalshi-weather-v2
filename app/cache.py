from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models import TickerUpdateEvent, TradeEvent


@dataclass
class MarketCacheEntry:
    market_ticker: str
    best_yes_bid: int = 0
    best_no_bid: int = 0
    top_yes_qty: int = 0
    top_no_qty: int = 0
    last_trade_price: int | None = None
    last_trade_side: str | None = None
    last_trade_qty: int | None = None
    last_update_at: datetime | None = None


@dataclass
class WebsocketState:
    connected: bool = False
    last_update_at: datetime | None = None
    markets: dict[str, MarketCacheEntry] = field(default_factory=dict)

    def mark_connected(self) -> None:
        self.connected = True

    def mark_disconnected(self) -> None:
        self.connected = False

    def apply_ticker_update(self, update: TickerUpdateEvent) -> MarketCacheEntry:
        entry = self.markets.get(update.market_ticker) or MarketCacheEntry(market_ticker=update.market_ticker)
        entry.best_yes_bid = update.best_yes_bid
        entry.best_no_bid = update.best_no_bid
        entry.top_yes_qty = update.top_yes_qty
        entry.top_no_qty = update.top_no_qty
        entry.last_update_at = update.received_at
        self.last_update_at = update.received_at
        self.markets[update.market_ticker] = entry
        return entry

    def apply_trade_update(self, update: TradeEvent) -> MarketCacheEntry:
        entry = self.markets.get(update.market_ticker) or MarketCacheEntry(market_ticker=update.market_ticker)
        entry.last_trade_price = update.price
        entry.last_trade_side = update.side
        entry.last_trade_qty = update.quantity
        entry.last_update_at = update.received_at
        self.last_update_at = update.received_at
        self.markets[update.market_ticker] = entry
        return entry


state = WebsocketState()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
