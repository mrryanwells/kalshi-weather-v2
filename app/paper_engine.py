from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlmodel import select

from app.db import get_session
from app.models import MarketSnapshot, PaperFill, PaperOrder


class PaperOrderCreate(BaseModel):
    market_ticker: str
    side: str
    action: str
    limit_price: int
    quantity: int
    notes: str | None = None


@dataclass
class FillDecision:
    should_fill: bool
    fill_price: int
    fill_qty: int


class PositionView(BaseModel):
    market_ticker: str
    side: str
    quantity: int
    avg_cost: float
    mark_price: float
    realized_pl: float
    unrealized_pl: float
    status: str


class PaperTradingEngine:
    """Conservative assumptions:
    - Fill only if limit crosses current executable price.
    - Fill quantity capped by top-of-book displayed liquidity.
    - No short selling: sell qty cannot exceed current long qty.
    - Orders are evaluated immediately against latest snapshot.
    """

    def place_order(self, payload: PaperOrderCreate) -> PaperOrder:
        now = datetime.now(timezone.utc)
        order = PaperOrder(
            created_at=now,
            market_ticker=payload.market_ticker,
            side=payload.side,
            action=payload.action,
            limit_price=payload.limit_price,
            quantity=payload.quantity,
            filled_quantity=0,
            status="open",
            notes=payload.notes,
        )
        with get_session() as session:
            session.add(order)
            session.commit()
            session.refresh(order)

        self.try_fill_order(order.id)
        with get_session() as session:
            refreshed = session.get(PaperOrder, order.id)
            assert refreshed is not None
            return refreshed

    def try_fill_order(self, order_id: int) -> None:
        with get_session() as session:
            order = session.get(PaperOrder, order_id)
            if order is None or order.status != "open":
                return
            latest_snapshot = session.exec(
                select(MarketSnapshot)
                .where(MarketSnapshot.market_ticker == order.market_ticker)
                .order_by(MarketSnapshot.captured_at.desc())
                .limit(1)
            ).first()
            if latest_snapshot is None:
                return

            current_positions = self._position_qty(session, order.market_ticker, order.side)
            decision = simulate_fill(order, latest_snapshot, current_positions)
            if not decision.should_fill:
                return

            order.filled_quantity += decision.fill_qty
            order.status = "filled" if order.filled_quantity >= order.quantity else "open"
            fill = PaperFill(
                created_at=datetime.now(timezone.utc),
                order_id=order.id,
                market_ticker=order.market_ticker,
                side=order.side,
                action=order.action,
                price=decision.fill_price,
                quantity=decision.fill_qty,
            )
            session.add(fill)
            session.add(order)
            session.commit()

    def list_orders(self) -> list[PaperOrder]:
        with get_session() as session:
            return session.exec(select(PaperOrder).order_by(PaperOrder.created_at.desc())).all()

    def list_fills(self) -> list[PaperFill]:
        with get_session() as session:
            return session.exec(select(PaperFill).order_by(PaperFill.created_at.desc())).all()

    def positions(self) -> list[PositionView]:
        with get_session() as session:
            fills = session.exec(select(PaperFill)).all()
            latest_by_market: dict[str, MarketSnapshot] = {}
            for snapshot in session.exec(select(MarketSnapshot).order_by(MarketSnapshot.captured_at.desc())).all():
                latest_by_market.setdefault(snapshot.market_ticker, snapshot)

        grouped: dict[tuple[str, str], list[PaperFill]] = defaultdict(list)
        for fill in fills:
            grouped[(fill.market_ticker, fill.side)].append(fill)

        views: list[PositionView] = []
        for (market_ticker, side), rows in grouped.items():
            qty, avg_cost, realized = position_lifecycle(rows)
            mark = mark_price_for_side(latest_by_market.get(market_ticker), side)
            unrealized = (mark - avg_cost) * qty if qty > 0 else 0.0
            views.append(
                PositionView(
                    market_ticker=market_ticker,
                    side=side,
                    quantity=qty,
                    avg_cost=round(avg_cost, 4),
                    mark_price=round(mark, 4),
                    realized_pl=round(realized, 4),
                    unrealized_pl=round(unrealized, 4),
                    status="open" if qty > 0 else "closed",
                )
            )
        return sorted(views, key=lambda x: (x.status, x.market_ticker, x.side))

    def trades_csv(self) -> str:
        fills = self.list_fills()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["created_at", "market_ticker", "side", "action", "price", "quantity"])
        for fill in fills:
            writer.writerow([fill.created_at.isoformat(), fill.market_ticker, fill.side, fill.action, fill.price, fill.quantity])
        return buf.getvalue()

    @staticmethod
    def _position_qty(session, market_ticker: str, side: str) -> int:
        fills = session.exec(
            select(PaperFill).where(PaperFill.market_ticker == market_ticker).where(PaperFill.side == side)
        ).all()
        qty = 0
        for fill in fills:
            qty += fill.quantity if fill.action == "buy" else -fill.quantity
        return max(qty, 0)


def executable_price(snapshot: MarketSnapshot, side: str, action: str) -> tuple[int, int]:
    if side == "yes" and action == "buy":
        return snapshot.implied_yes_ask, snapshot.top_no_qty
    if side == "yes" and action == "sell":
        return snapshot.best_yes_bid, snapshot.top_yes_qty
    if side == "no" and action == "buy":
        implied_no_ask = 100 - snapshot.best_yes_bid
        return implied_no_ask, snapshot.top_yes_qty
    return snapshot.best_no_bid, snapshot.top_no_qty


def simulate_fill(order: PaperOrder, snapshot: MarketSnapshot, current_position_qty: int = 0) -> FillDecision:
    price, available_qty = executable_price(snapshot, order.side, order.action)
    remaining = max(0, order.quantity - order.filled_quantity)
    if order.action == "sell" and current_position_qty <= 0:
        return FillDecision(False, price, 0)
    if order.action == "sell":
        remaining = min(remaining, current_position_qty)

    crosses = order.limit_price >= price if order.action == "buy" else order.limit_price <= price
    fill_qty = min(remaining, max(0, available_qty))
    return FillDecision(crosses and fill_qty > 0, price, fill_qty if crosses else 0)


def position_lifecycle(fills: list[PaperFill]) -> tuple[int, float, float]:
    qty = 0
    avg_cost = 0.0
    realized = 0.0
    for fill in sorted(fills, key=lambda x: x.created_at):
        if fill.action == "buy":
            new_cost = avg_cost * qty + fill.price * fill.quantity
            qty += fill.quantity
            avg_cost = new_cost / qty if qty > 0 else 0.0
        else:
            close_qty = min(qty, fill.quantity)
            realized += (fill.price - avg_cost) * close_qty
            qty -= close_qty
            if qty == 0:
                avg_cost = 0.0
    return qty, avg_cost, realized


def mark_price_for_side(snapshot: MarketSnapshot | None, side: str) -> float:
    if snapshot is None:
        return 0.0
    if side == "yes":
        return (snapshot.best_yes_bid + snapshot.implied_yes_ask) / 2
    implied_no_ask = 100 - snapshot.best_yes_bid
    return (snapshot.best_no_bid + implied_no_ask) / 2
