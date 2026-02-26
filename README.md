# kalshi-temp-scanner

See `docs/assumptions.md` for the modeling sanity anchor (fields, fill/settlement assumptions, and estimated-vs-exact boundaries).

Read-only scanner + websocket monitor + paper trading simulator + snapshot backtesting for Kalshi temperature markets.

## Features
- Public market scanning (`/markets`, `/orderbook`) with SQLite snapshots.
- Opportunity metrics and ranking dashboard.
- WebSocket market data (`ticker`, `trade`) with reconnect/backoff.
- Paper trading engine (no real order placement, no authenticated calls).
- Backtesting module that replays stored snapshots with deterministic ordering and parameterized thresholds.

## Paper trading assumptions (conservative)
- Orders fill only when limit crosses current executable top-of-book price.
- Fill size capped by top-of-book displayed liquidity.
- Sell orders capped by existing long paper position (no shorting).
- Orders evaluated against latest snapshot data.

## Backtesting
- Reuses strategy ranking and paper fill simulation logic.
- Date-range replay over stored `MarketSnapshot` rows.
- Stores each run and summary metrics in DB.
- Metrics:
  - number of trades
  - win rate
  - realized P/L
  - average P/L per trade
  - max drawdown
  - P/L by hour bucket
- UI:
  - `GET /backtests` run list + run form
  - `GET /backtests/{run_id}` run details

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

## Example backtest command
After app is running and snapshots exist:
```bash
curl -X POST http://localhost:8000/backtests/run \
  -F start_at=2026-01-01T00:00:00+00:00 \
  -F end_at=2026-01-02T00:00:00+00:00 \
  -F min_score=0.25 \
  -F max_spread=8 \
  -F side=yes \
  -F quantity=1
```

## Main routes
- `GET /` dashboard
- `GET /paper/trades`
- `GET /paper/positions`
- `GET /backtests`
- `GET /backtests/{run_id}`
- `GET /api/opportunities`
- `GET /api/markets/{ticker}`
- `GET /api/ws-status`
- `GET /api/paper/orders`
- `GET /api/paper/positions`
- `GET /api/paper/trades.csv`

## Testing
```bash
pytest
```
