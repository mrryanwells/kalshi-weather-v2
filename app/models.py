from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


class MarketSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    captured_at: datetime = Field(index=True)
    market_ticker: str = Field(index=True)
    series_ticker: str = Field(index=True)
    close_time: datetime | None = Field(default=None, index=True)
    best_yes_bid: int
    best_no_bid: int
    implied_yes_ask: int
    spread: int
    top_yes_qty: int
    top_no_qty: int
    score: float = Field(index=True)
    raw_orderbook: str


class Opportunity(BaseModel):
    market_ticker: str
    series_ticker: str
    close_time: datetime | None
    best_yes_bid: int
    best_no_bid: int
    implied_yes_ask: int
    spread: int
    top_yes_qty: int
    top_no_qty: int
    score: float


class KalshiMarket(BaseModel):
    ticker: str
    series_ticker: str
    close_time: datetime | None = None


class KalshiOrderbook(BaseModel):
    market_ticker: str
    yes: list[list[int]] = PydanticField(default_factory=list)
    no: list[list[int]] = PydanticField(default_factory=list)
    raw: dict[str, Any] = PydanticField(default_factory=dict)


class PaperOrder(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(index=True)
    market_ticker: str = Field(index=True)
    side: str = Field(index=True)
    action: str
    limit_price: int
    quantity: int
    filled_quantity: int = 0
    status: str = Field(default="open", index=True)
    notes: str | None = None


class PaperFill(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(index=True)
    order_id: int = Field(index=True)
    market_ticker: str = Field(index=True)
    side: str = Field(index=True)
    action: str
    price: int
    quantity: int


class BacktestRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(index=True)
    start_at: datetime = Field(index=True)
    end_at: datetime = Field(index=True)
    min_score: float
    max_spread: int
    side: str
    quantity: int
    num_trades: int
    win_rate: float
    realized_pl: float
    avg_pl_per_trade: float
    max_drawdown: float
    pnl_by_hour_json: str


class BacktestTrade(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    market_ticker: str = Field(index=True)
    entry_time: datetime
    exit_time: datetime
    entry_price: int
    exit_price: int
    quantity: int
    pnl: float


class TickerUpdateEvent(BaseModel):
    type: Literal["ticker"] = "ticker"
    market_ticker: str
    best_yes_bid: int
    best_no_bid: int
    top_yes_qty: int
    top_no_qty: int
    received_at: datetime = PydanticField(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = PydanticField(default_factory=dict)


class TradeEvent(BaseModel):
    type: Literal["trade"] = "trade"
    market_ticker: str
    price: int
    side: str
    quantity: int
    received_at: datetime = PydanticField(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = PydanticField(default_factory=dict)


class WebsocketStatus(BaseModel):
    connected: bool
    last_update_at: datetime | None
