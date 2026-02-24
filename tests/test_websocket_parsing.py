from __future__ import annotations

from app.kalshi_websocket_client import parse_ws_message
from app.models import TickerUpdateEvent, TradeEvent


def test_parse_ticker_message() -> None:
    payload = {
        "type": "ticker",
        "data": {
            "market_ticker": "KXHIGHNY-24DEC31-B35",
            "best_yes_bid": 45,
            "best_no_bid": 53,
            "top_yes_qty": 111,
            "top_no_qty": 222,
        },
    }

    events = parse_ws_message(payload)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, TickerUpdateEvent)
    assert event.best_yes_bid == 45
    assert event.best_no_bid == 53


def test_parse_trade_message() -> None:
    payload = {
        "type": "trade",
        "data": {
            "market_ticker": "KXHIGHNY-24DEC31-B35",
            "price": 49,
            "side": "yes",
            "quantity": 10,
        },
    }

    events = parse_ws_message(payload)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, TradeEvent)
    assert event.price == 49
    assert event.quantity == 10
