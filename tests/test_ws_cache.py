from __future__ import annotations

from app.cache import WebsocketState
from app.models import TickerUpdateEvent, TradeEvent


def test_cache_applies_ticker_update() -> None:
    cache = WebsocketState()
    entry = cache.apply_ticker_update(
        TickerUpdateEvent(
            market_ticker="KXHIGHNY-24DEC31-B35",
            best_yes_bid=44,
            best_no_bid=55,
            top_yes_qty=100,
            top_no_qty=95,
        )
    )

    assert entry.best_yes_bid == 44
    assert entry.best_no_bid == 55
    assert cache.last_update_at is not None


def test_cache_applies_trade_update() -> None:
    cache = WebsocketState()
    entry = cache.apply_trade_update(
        TradeEvent(
            market_ticker="KXHIGHNY-24DEC31-B35",
            price=48,
            side="no",
            quantity=12,
        )
    )

    assert entry.last_trade_price == 48
    assert entry.last_trade_side == "no"
    assert entry.last_trade_qty == 12
