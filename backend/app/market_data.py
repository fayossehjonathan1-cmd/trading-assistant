"""Récupération des prix de marché : Twelve Data en production, générateur random-walk en mock."""
from __future__ import annotations

import logging
import math
import random
import time

import httpx

from .indicators import adx, atr, atr_series, rsi

logger = logging.getLogger(__name__)

RETRIES = 3
RETRY_DELAY = 2.0


class MarketDataError(Exception):
    pass


def _snapshot_from_candles(display_symbol: str, candles: list[dict], donchian: int = 10) -> dict:
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    atrs = atr_series(highs, lows, closes)
    atr_avg = sum(atrs[-20:]) / len(atrs[-20:]) if atrs else None
    price = closes[-1]
    n = donchian + 1
    return {
        "actif": display_symbol,
        "prix": price,
        "rsi": rsi(closes),
        "atr": atr(highs, lows, closes),
        "atr_moyen": round(atr_avg, 6) if atr_avg else None,
        "adx": adx(highs, lows, closes),
        "variation_pct": round((closes[-1] / closes[-13] - 1) * 100, 3) if len(closes) >= 13 else None,
        # canal Donchian: N bougies précédentes, bougie courante exclue (détection de cassure)
        "donchian_periode": donchian,
        "plus_haut_recent": max(highs[-n:-1]) if len(highs) >= n else max(highs[:-1] or highs),
        "plus_bas_recent": min(lows[-n:-1]) if len(lows) >= n else min(lows[:-1] or lows),
        "candles": candles[-10:],  # contexte récent pour le prompt Claude
    }


class TwelveDataClient:
    """Client Twelve Data — 1 crédit API par actif et par cycle (série OHLC), indicateurs calculés localement."""

    BASE = "https://api.twelvedata.com"

    def __init__(self, api_key: str, interval: str = "5min", donchian: int = 10):
        self.api_key = api_key
        self.interval = interval
        self.donchian = donchian
        self._client = httpx.Client(timeout=20)

    def get_snapshot(self, display_symbol: str, td_symbol: str) -> dict:
        candles = self._time_series(td_symbol, interval=self.interval)
        return _snapshot_from_candles(display_symbol, candles, self.donchian)

    def _time_series(self, symbol: str, interval: str = "5min", outputsize: int = 120) -> list[dict]:
        last_err: Exception | None = None
        for attempt in range(RETRIES):
            try:
                resp = self._client.get(f"{self.BASE}/time_series", params={
                    "symbol": symbol, "interval": interval,
                    "outputsize": outputsize, "apikey": self.api_key,
                })
                data = resp.json()
                if data.get("status") == "error" or "values" not in data:
                    raise MarketDataError(f"Twelve Data: {data.get('message', 'réponse invalide')}")
                values = list(reversed(data["values"]))  # API renvoie du plus récent au plus ancien
                return [{
                    "time": v["datetime"],
                    "open": float(v["open"]), "high": float(v["high"]),
                    "low": float(v["low"]), "close": float(v["close"]),
                } for v in values]
            except Exception as exc:  # réseau, quota, parse — on retente puis on remonte
                last_err = exc
                logger.warning("Twelve Data tentative %d/%d échouée pour %s: %s", attempt + 1, RETRIES, symbol, exc)
                time.sleep(RETRY_DELAY * (attempt + 1))
        raise MarketDataError(f"Twelve Data indisponible pour {symbol}: {last_err}")


class MockMarketData:
    """Random walk persistant par actif — permet de tester tout le pipeline sans clé API."""

    BASE_PRICES = {"XAUUSD": 3350.0, "EURUSD": 1.0850, "BTCUSD": 108000.0}

    def __init__(self, donchian: int = 10):
        self.donchian = donchian
        self._series: dict[str, list[dict]] = {}

    def get_snapshot(self, display_symbol: str, td_symbol: str) -> dict:
        candles = self._series.setdefault(display_symbol, self._seed(display_symbol))
        self._advance(display_symbol, candles)
        return _snapshot_from_candles(display_symbol, candles[-120:], self.donchian)

    def _seed(self, symbol: str) -> list[dict]:
        rng = random.Random(hash(symbol) & 0xFFFF)
        price = self.BASE_PRICES.get(symbol, 100.0)
        vol = price * 0.0012
        candles = []
        trend = 0.0
        for i in range(150):
            if i % 30 == 0:
                trend = rng.uniform(-0.4, 0.4) * vol  # phases de tendance / range
            drift = trend + rng.gauss(0, vol)
            o = price
            c = max(price + drift, price * 0.5)
            h = max(o, c) + abs(rng.gauss(0, vol * 0.4))
            l = min(o, c) - abs(rng.gauss(0, vol * 0.4))
            candles.append({"time": f"t-{150 - i}", "open": round(o, 5), "high": round(h, 5),
                            "low": round(l, 5), "close": round(c, 5)})
            price = c
        return candles

    def _advance(self, symbol: str, candles: list[dict]) -> None:
        rng = random.Random()
        last = candles[-1]["close"]
        vol = last * 0.0012
        o = last
        c = max(last + rng.gauss(0, vol) + math.sin(time.time() / 600) * vol * 0.3, last * 0.5)
        h = max(o, c) + abs(rng.gauss(0, vol * 0.4))
        l = min(o, c) - abs(rng.gauss(0, vol * 0.4))
        candles.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "open": round(o, 5),
                        "high": round(h, 5), "low": round(l, 5), "close": round(c, 5)})
        if len(candles) > 500:
            del candles[:len(candles) - 300]
