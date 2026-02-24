from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlmodel import select

from app.db import get_session
from app.models import BacktestRun, BacktestTrade, MarketSnapshot, PaperOrder
from app.paper_engine import simulate_fill
from app.strategy import ranking_score


class BacktestParams(BaseModel):
    start_at: datetime
    end_at: datetime
    min_score: float = 0.2
    max_spread: int = 10
    side: str = "yes"
    quantity: int = 1


@dataclass
class ReplayTrade:
    market_ticker: str
    entry_time: datetime
    exit_time: datetime
    entry_price: int
    exit_price: int
    pnl: float


class BacktestSummary(BaseModel):
    num_trades: int
    win_rate: float
    realized_pl: float
    avg_pl_per_trade: float
    max_drawdown: float
    pnl_by_hour: dict[str, float]


class BacktestEngine:
    def run(self, params: BacktestParams) -> BacktestRun:
        snapshots = self._load_snapshots(params)
        trades = replay_snapshots(snapshots, params)
        summary = calculate_metrics(trades)

        run = BacktestRun(
            created_at=datetime.utcnow(),
            start_at=params.start_at,
            end_at=params.end_at,
            min_score=params.min_score,
            max_spread=params.max_spread,
            side=params.side,
            quantity=params.quantity,
            num_trades=summary.num_trades,
            win_rate=summary.win_rate,
            realized_pl=summary.realized_pl,
            avg_pl_per_trade=summary.avg_pl_per_trade,
            max_drawdown=summary.max_drawdown,
            pnl_by_hour_json=str(summary.pnl_by_hour),
        )
        with get_session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            for t in trades:
                session.add(
                    BacktestTrade(
                        run_id=run.id,
                        market_ticker=t.market_ticker,
                        entry_time=t.entry_time,
                        exit_time=t.exit_time,
                        entry_price=t.entry_price,
                        exit_price=t.exit_price,
                        quantity=params.quantity,
                        pnl=t.pnl,
                    )
                )
            session.commit()
        return run

    def list_runs(self) -> list[BacktestRun]:
        with get_session() as session:
            return session.exec(select(BacktestRun).order_by(BacktestRun.created_at.desc())).all()

    def run_details(self, run_id: int) -> tuple[BacktestRun | None, list[BacktestTrade]]:
        with get_session() as session:
            run = session.get(BacktestRun, run_id)
            if run is None:
                return None, []
            trades = session.exec(select(BacktestTrade).where(BacktestTrade.run_id == run_id).order_by(BacktestTrade.entry_time)).all()
            return run, trades

    @staticmethod
    def _load_snapshots(params: BacktestParams) -> list[MarketSnapshot]:
        with get_session() as session:
            rows = session.exec(
                select(MarketSnapshot)
                .where(MarketSnapshot.captured_at >= params.start_at)
                .where(MarketSnapshot.captured_at <= params.end_at)
                .order_by(MarketSnapshot.captured_at, MarketSnapshot.id)
            ).all()
        # deterministic stable order
        return rows


def replay_snapshots(snapshots: list[MarketSnapshot], params: BacktestParams) -> list[ReplayTrade]:
    trades: list[ReplayTrade] = []
    open_positions: dict[str, tuple[datetime, int]] = {}

    for snap in snapshots:
        score = ranking_score(snap.spread, snap.top_yes_qty, snap.top_no_qty, snap.close_time, now=snap.captured_at)
        if score < params.min_score or snap.spread > params.max_spread:
            continue

        if snap.market_ticker not in open_positions:
            order = PaperOrder(
                created_at=snap.captured_at,
                market_ticker=snap.market_ticker,
                side=params.side,
                action="buy",
                limit_price=99,
                quantity=params.quantity,
                filled_quantity=0,
                status="open",
            )
            decision = simulate_fill(order, snap, 0)
            if decision.should_fill and decision.fill_qty >= params.quantity:
                open_positions[snap.market_ticker] = (snap.captured_at, decision.fill_price)
            continue

        entry_time, entry_price = open_positions[snap.market_ticker]
        exit_order = PaperOrder(
            created_at=snap.captured_at,
            market_ticker=snap.market_ticker,
            side=params.side,
            action="sell",
            limit_price=0,
            quantity=params.quantity,
            filled_quantity=0,
            status="open",
        )
        exit_decision = simulate_fill(exit_order, snap, params.quantity)
        if exit_decision.should_fill:
            pnl = (exit_decision.fill_price - entry_price) * params.quantity
            trades.append(
                ReplayTrade(
                    market_ticker=snap.market_ticker,
                    entry_time=entry_time,
                    exit_time=snap.captured_at,
                    entry_price=entry_price,
                    exit_price=exit_decision.fill_price,
                    pnl=pnl,
                )
            )
            del open_positions[snap.market_ticker]

    return trades


def calculate_metrics(trades: list[ReplayTrade]) -> BacktestSummary:
    num = len(trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    realized = sum(t.pnl for t in trades)
    avg = realized / num if num else 0.0

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    by_hour: dict[str, float] = defaultdict(float)
    for t in sorted(trades, key=lambda x: x.exit_time):
        equity += t.pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        by_hour[t.exit_time.strftime("%H:00")] += t.pnl

    return BacktestSummary(
        num_trades=num,
        win_rate=(wins / num) if num else 0.0,
        realized_pl=realized,
        avg_pl_per_trade=avg,
        max_drawdown=abs(max_dd),
        pnl_by_hour=dict(sorted(by_hour.items())),
    )
