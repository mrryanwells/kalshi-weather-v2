from __future__ import annotations

import asyncio

import pytest

from app.kalshi_websocket_client import KalshiWebSocketClient


@pytest.mark.asyncio
async def test_run_forever_backoff_and_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KalshiWebSocketClient()
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    async def fake_session(tracked_tickers: list[str]) -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary")
        client.stop()

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(client, "_run_session", fake_session)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await client.run_forever(["KXHIGHNY-24DEC31-B35"])

    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 2.0]
