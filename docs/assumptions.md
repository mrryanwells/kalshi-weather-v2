# Assumptions & Modeling Notes

This document is the project sanity anchor. Keep it updated whenever data usage, pricing, fills, or settlement logic changes.

## 1) Kalshi fields currently used

### REST market list (`/markets`)
- `ticker`
- `series_ticker`
- `close_time`

### REST orderbook (`/markets/{ticker}/orderbook`)
- `orderbook.yes` (top-of-book price/qty from first level)
- `orderbook.no` (top-of-book price/qty from first level)

### WebSocket (`ticker`, `trade`)
Ticker channel:
- `market_ticker` (or fallback `ticker`)
- `best_yes_bid` (or fallback `yes_bid`)
- `best_no_bid` (or fallback `no_bid`)
- `top_yes_qty` (or fallback `yes_bid_qty`)
- `top_no_qty` (or fallback `no_bid_qty`)

Trade channel:
- `market_ticker` (or fallback `ticker`)
- `price`
- `side`
- `quantity` (or fallback `count`)

## 2) Fill assumptions in paper trading

Current paper engine is intentionally conservative:
- Fill only if the limit crosses executable top-of-book price.
- Fill quantity capped at top-of-book displayed liquidity.
- Sell quantity capped by current long paper position (no shorting).
- Orders are evaluated against latest available snapshot, not full depth evolution.
- No slippage model beyond top-of-book cap.
- No queue-position or latency model.

Executable price conventions:
- YES buy uses implied YES ask = `100 - best_no_bid`.
- YES sell uses `best_yes_bid`.
- NO buy uses implied NO ask = `100 - best_yes_bid`.
- NO sell uses `best_no_bid`.

## 3) Settlement assumptions for temperature markets

For current scanner/backtest scope:
- Settlement is **not** modeled from official final weather observations yet.
- Realized P/L is derived only from simulated exits during replay/paper flow.
- Open-position carry/expiry settlement rules are currently out of scope.

When settlement support is added, document:
- official source of observed temperature,
- timezone/cutoff handling,
- tie/bucket edge handling,
- late revisions policy.

## 4) Estimated vs exact

### Exact (from stored snapshot / event payload)
- top-of-book bids and top sizes used in metrics
- captured timestamps
- stored scanner spread metric and ranking inputs

### Estimated / modeled
- implied asks (`100 - opposite_bid`)
- fill outcomes and sizes in paper mode
- backtest trade sequence from snapshot replay
- drawdown/equity path derived from replayed fills

## 5) Update checklist

Update this file when any of the following changes:
- parsed Kalshi payload fields (REST or WS)
- fill simulation rules
- P/L accounting or position lifecycle rules
- settlement modeling
- deterministic replay ordering rules
