"""Indicateurs techniques calculés en pur Python (pas de dépendance native).

Toutes les fonctions attendent des listes ordonnées du plus ancien au plus récent.
Lissage de Wilder pour RSI / ATR / ADX (valeurs conformes aux plateformes de trading).
"""
from __future__ import annotations


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 2)


def _true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return trs


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs = _true_ranges(highs, lows, closes)
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return round(value, 6)


def atr_series(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Série d'ATR lissés (pour comparer l'ATR courant à sa moyenne récente)."""
    if len(closes) < period + 1:
        return []
    trs = _true_ranges(highs, lows, closes)
    value = sum(trs[:period]) / period
    series = [value]
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
        series.append(value)
    return series


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < 2 * period + 1:
        return None
    plus_dm, minus_dm = [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    trs = _true_ranges(highs, lows, closes)

    sm_tr = sum(trs[:period])
    sm_plus = sum(plus_dm[:period])
    sm_minus = sum(minus_dm[:period])
    dxs = []
    for i in range(period, len(trs)):
        sm_tr = sm_tr - sm_tr / period + trs[i]
        sm_plus = sm_plus - sm_plus / period + plus_dm[i]
        sm_minus = sm_minus - sm_minus / period + minus_dm[i]
        if sm_tr == 0:
            dxs.append(0.0)
            continue
        plus_di = 100.0 * sm_plus / sm_tr
        minus_di = 100.0 * sm_minus / sm_tr
        di_sum = plus_di + minus_di
        dxs.append(100.0 * abs(plus_di - minus_di) / di_sum if di_sum else 0.0)

    if len(dxs) < period:
        return None
    value = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        value = (value * (period - 1) + dx) / period
    return round(value, 2)
