from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.backtest import BacktestEngine, BacktestParams
from app.cache import state
from app.config import get_settings
from app.db import create_db_and_tables
from app.kalshi_websocket_client import KalshiWebSocketClient
from app.models import WebsocketStatus
from app.paper_engine import PaperOrderCreate, PaperTradingEngine
from app.scanner import ScannerService

settings = get_settings()
app = FastAPI(title=settings.app_name)
templates = Jinja2Templates(directory="app/templates")
scanner = ScannerService()
paper_engine = PaperTradingEngine()
backtest_engine = BacktestEngine()
ws_client = KalshiWebSocketClient()
ws_task: asyncio.Task | None = None
scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup() -> None:
    global ws_task
    create_db_and_tables()
    if not scheduler.running:
        scheduler.add_job(scanner.scan_once, "interval", seconds=settings.scan_interval_seconds, max_instances=1)
        scheduler.start()
    if settings.websocket_enabled and ws_task is None:
        tracked_tickers = await scanner.tracked_market_tickers()
        ws_task = asyncio.create_task(ws_client.run_forever(tracked_tickers))


@app.on_event("shutdown")
async def shutdown() -> None:
    global ws_task
    if scheduler.running:
        scheduler.shutdown(wait=False)
    ws_client.stop()
    if ws_task is not None:
        ws_task.cancel()
        ws_task = None


def _dashboard_context(
    request: Request,
    *,
    series_ticker: str | None,
    max_spread: int,
    min_yes_qty: int,
    min_no_qty: int,
    min_score: float | None,
    price_min: int,
    price_max: int,
    actionable_only: bool,
    sort_by: str,
    market_ticker: str,
    side: str,
    action: str,
    limit_price: int | None,
    quantity: int,
) -> dict:
    rows = scanner.latest_market_rows(
        series_ticker=series_ticker,
        max_spread=max_spread,
        min_yes_qty=min_yes_qty,
        min_no_qty=min_no_qty,
        min_score=min_score,
        price_min=price_min,
        price_max=price_max,
        actionable_only=actionable_only,
        sort_by=sort_by,
        limit=200,
    )
    return {
        "request": request,
        "rows": rows,
        "series_tickers": settings.series_tickers,
        "ws_status": WebsocketStatus(connected=state.connected, last_update_at=state.last_update_at),
        "last_refresh_time": datetime.now(timezone.utc),
        "filters": {
            "series_ticker": series_ticker or "",
            "max_spread": max_spread,
            "min_yes_qty": min_yes_qty,
            "min_no_qty": min_no_qty,
            "min_score": "" if min_score is None else min_score,
            "price_min": price_min,
            "price_max": price_max,
            "actionable_only": actionable_only,
            "sort_by": sort_by,
        },
        "prefill": {
            "market_ticker": market_ticker,
            "side": side,
            "action": action,
            "limit_price": "" if limit_price is None else limit_price,
            "quantity": quantity,
        },
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    series_ticker: str | None = Query(default=None),
    max_spread: int = Query(default=3),
    min_yes_qty: int = Query(default=50),
    min_no_qty: int = Query(default=50),
    min_score: float | None = Query(default=None),
    price_min: int = Query(default=15),
    price_max: int = Query(default=85),
    actionable_only: bool = Query(default=True),
    sort_by: str = Query(default="score_desc"),
    market_ticker: str = Query(default=""),
    side: str = Query(default="yes"),
    action: str = Query(default="buy"),
    limit_price: int | None = Query(default=None),
    quantity: int = Query(default=1),
) -> HTMLResponse:
    context = _dashboard_context(
        request,
        series_ticker=series_ticker,
        max_spread=max_spread,
        min_yes_qty=min_yes_qty,
        min_no_qty=min_no_qty,
        min_score=min_score,
        price_min=price_min,
        price_max=price_max,
        actionable_only=actionable_only,
        sort_by=sort_by,
        market_ticker=market_ticker,
        side=side,
        action=action,
        limit_price=limit_price,
        quantity=quantity,
    )
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/dashboard/opportunities", response_class=HTMLResponse)
async def dashboard_opportunities_partial(
    request: Request,
    series_ticker: str | None = Query(default=None),
    max_spread: int = Query(default=3),
    min_yes_qty: int = Query(default=50),
    min_no_qty: int = Query(default=50),
    min_score: float | None = Query(default=None),
    price_min: int = Query(default=15),
    price_max: int = Query(default=85),
    actionable_only: bool = Query(default=True),
    sort_by: str = Query(default="score_desc"),
) -> HTMLResponse:
    context = _dashboard_context(
        request,
        series_ticker=series_ticker,
        max_spread=max_spread,
        min_yes_qty=min_yes_qty,
        min_no_qty=min_no_qty,
        min_score=min_score,
        price_min=price_min,
        price_max=price_max,
        actionable_only=actionable_only,
        sort_by=sort_by,
        market_ticker="",
        side="yes",
        action="buy",
        limit_price=None,
        quantity=1,
    )
    return templates.TemplateResponse("_opportunities_table.html", context)


@app.get("/markets/{ticker}", response_class=HTMLResponse)
async def market_detail_page(request: Request, ticker: str) -> HTMLResponse:
    history = scanner.get_market_history(ticker=ticker)
    if not history:
        raise HTTPException(status_code=404, detail="Market not found")
    return templates.TemplateResponse("market_detail.html", {"request": request, "ticker": ticker, "history": history})


@app.post("/paper/orders")
async def create_paper_order(
    market_ticker: str = Form(...),
    side: str = Form(...),
    action: str = Form(...),
    limit_price: int = Form(...),
    quantity: int = Form(...),
    notes: str | None = Form(default=None),
) -> RedirectResponse:
    paper_engine.place_order(
        PaperOrderCreate(
            market_ticker=market_ticker,
            side=side,
            action=action,
            limit_price=limit_price,
            quantity=quantity,
            notes=notes,
        )
    )
    return RedirectResponse(url="/paper/trades", status_code=303)


@app.get("/paper/trades", response_class=HTMLResponse)
async def paper_trades(request: Request) -> HTMLResponse:
    fills = paper_engine.list_fills()
    orders = {o.id: o for o in paper_engine.list_orders()}
    rows = [{**fill.model_dump(), "notes": (orders.get(fill.order_id).notes if orders.get(fill.order_id) else None)} for fill in fills]
    return templates.TemplateResponse("paper_trades.html", {"request": request, "rows": rows})


@app.get("/paper/positions", response_class=HTMLResponse)
async def paper_positions(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("paper_positions.html", {"request": request, "rows": paper_engine.positions()})


@app.get("/backtests", response_class=HTMLResponse)
async def backtests_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("backtests.html", {"request": request, "runs": backtest_engine.list_runs()})


@app.post("/backtests/run")
async def run_backtest(
    start_at: str = Form(...),
    end_at: str = Form(...),
    min_score: float = Form(0.2),
    max_spread: int = Form(10),
    side: str = Form("yes"),
    quantity: int = Form(1),
) -> RedirectResponse:
    run = backtest_engine.run(
        BacktestParams(
            start_at=datetime.fromisoformat(start_at),
            end_at=datetime.fromisoformat(end_at),
            min_score=min_score,
            max_spread=max_spread,
            side=side,
            quantity=quantity,
        )
    )
    return RedirectResponse(url=f"/backtests/{run.id}", status_code=303)


@app.get("/backtests/{run_id}", response_class=HTMLResponse)
async def backtest_details(request: Request, run_id: int) -> HTMLResponse:
    run, trades = backtest_engine.run_details(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return templates.TemplateResponse("backtest_detail.html", {"request": request, "run": run, "trades": trades})


@app.get("/api/paper/orders")
async def api_paper_orders() -> list[dict]:
    return [o.model_dump(mode="json") for o in paper_engine.list_orders()]


@app.get("/api/paper/positions")
async def api_paper_positions() -> list[dict]:
    return [p.model_dump(mode="json") for p in paper_engine.positions()]


@app.get("/api/paper/trades.csv")
async def api_paper_trades_csv() -> Response:
    return Response(content=paper_engine.trades_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=paper_trades.csv"})


@app.get("/api/opportunities")
async def api_opportunities(
    series_ticker: str | None = Query(default=None),
    max_spread: int = Query(default=3),
    min_depth: int | None = Query(default=None),
    min_yes_qty: int = Query(default=50),
    min_no_qty: int = Query(default=50),
    min_score: float | None = Query(default=None),
    price_min: int = Query(default=15),
    price_max: int = Query(default=85),
    actionable_only: bool = Query(default=True),
    sort_by: str = Query(default="score_desc"),
) -> list[dict]:
    return scanner.latest_market_rows(
        series_ticker=series_ticker,
        max_spread=max_spread,
        min_depth=min_depth,
        min_yes_qty=min_yes_qty,
        min_no_qty=min_no_qty,
        min_score=min_score,
        price_min=price_min,
        price_max=price_max,
        actionable_only=actionable_only,
        sort_by=sort_by,
        limit=200,
    )


@app.get("/api/markets/{ticker}")
async def api_market(ticker: str) -> list[dict]:
    history = scanner.get_market_history(ticker=ticker)
    if not history:
        raise HTTPException(status_code=404, detail="Market not found")
    return [row.model_dump(mode="json") for row in history]


@app.get("/api/ws-status")
async def api_ws_status() -> dict:
    return WebsocketStatus(connected=state.connected, last_update_at=state.last_update_at).model_dump(mode="json")
