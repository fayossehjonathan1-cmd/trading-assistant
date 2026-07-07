"""Exploration systématique de variantes de stratégie sur les données du backtest.

Réutilise le cache de bougies 5min (zéro appel API), résample localement en 15min/1h,
et teste une grille de configurations avec validation in-sample (janv-avril) /
out-of-sample (mai-juillet) pour écarter le sur-ajustement.

Usage: python sweep.py
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path

from app.indicators import adx, atr, atr_series, rsi
from app.regime import detect_regime
from backtest import _pos_r, _step_trade

CACHE_DIR = Path(__file__).parent / "backtest_cache"
ASSETS = ["XAUUSD", "EURUSD", "BTCUSD"]
CUTOFF = "2026-05-01"           # avant = in-sample (optimisation), après = out-of-sample (validation)
FRICTION = 0.05                 # coût estimé par trade, en R
COOLDOWN_MINUTES = 60
WARMUP = 170


# ---------------------------------------------------------------- données

def load_5min(display: str) -> list[dict]:
    return json.loads((CACHE_DIR / f"{display}_5min_6m.json").read_text())


def resample(candles: list[dict], minutes: int) -> list[dict]:
    if minutes == 5:
        return candles
    out: list[dict] = []
    cur_key, cur = None, None
    for c in candles:
        dt = datetime.strptime(c["time"], "%Y-%m-%d %H:%M:%S")
        floored = dt.replace(minute=0 if minutes >= 60 else (dt.minute // minutes) * minutes, second=0)
        key = floored.strftime("%Y-%m-%d %H:%M:%S")
        if key != cur_key:
            if cur:
                out.append(cur)
            cur_key = key
            cur = {"time": key, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}
        else:
            cur["high"] = max(cur["high"], c["high"])
            cur["low"] = min(cur["low"], c["low"])
            cur["close"] = c["close"]
    if cur:
        out.append(cur)
    return out


def precompute(candles: list[dict]) -> dict:
    """Indicateurs par bougie (indépendants de la config) — calculés une seule fois."""
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    n = len(candles)
    out = {"rsi": [None] * n, "atr": [None] * n, "regime": [None] * n, "sma50": [None] * n}
    for i in range(WARMUP, n):
        w0 = i - 119
        w_h, w_l, w_c = highs[w0:i + 1], lows[w0:i + 1], closes[w0:i + 1]
        atr_now = atr(w_h, w_l, w_c)
        atrs = atr_series(w_h, w_l, w_c)
        atr_avg = sum(atrs[-20:]) / len(atrs[-20:]) if atrs else None
        out["atr"][i] = atr_now
        out["rsi"][i] = rsi(w_c)
        out["regime"][i] = detect_regime(adx(w_h, w_l, w_c), atr_now, atr_avg)
        out["sma50"][i] = sum(closes[i - 49:i + 1]) / 50
    return out


# ---------------------------------------------------------------- stratégies

def gen_direction(mode: str, regime: str, rsi_now: float, close: float, sma50: float,
                  rsi_buy: float, rsi_sell: float) -> str | None:
    if mode == "actuel":  # mécanique actuelle: retour à la moyenne quel que soit le régime
        if rsi_now < rsi_buy:
            return "achat"
        if rsi_now > rsi_sell:
            return "vente"
        return None
    if mode == "range_seul":  # retour à la moyenne uniquement en range
        if regime != "range":
            return None
        if rsi_now < rsi_buy:
            return "achat"
        if rsi_now > rsi_sell:
            return "vente"
        return None
    if mode == "adaptatif":  # range: mean-reversion / tendance: pullback dans le sens SMA50
        if regime == "range":
            if rsi_now < rsi_buy:
                return "achat"
            if rsi_now > rsi_sell:
                return "vente"
        elif regime == "tendance":
            if close > sma50 and rsi_now < 50:
                return "achat"
            if close < sma50 and rsi_now > 50:
                return "vente"
        return None
    raise ValueError(mode)


# ---------------------------------------------------------------- simulation

def simulate(candles: list[dict], ind: dict, mode: str, rsi_buy: float, rsi_sell: float,
             stop_mult: float, interval_minutes: int) -> list[dict]:
    cooldown_bars = max(1, round(COOLDOWN_MINUTES / interval_minutes))
    closes = [c["close"] for c in candles]
    trades: list[dict] = []
    open_trade: dict | None = None
    last_sig = -(10 ** 9)

    for i in range(WARMUP, len(candles)):
        regime = ind["regime"][i]
        if open_trade is not None:
            if _step_trade(open_trade, candles[i], regime, i):
                open_trade["pnl_net"] = round(open_trade["pnl"] - FRICTION, 4)
                trades.append(open_trade)
                open_trade = None
            continue
        if i - last_sig < cooldown_bars:
            continue
        last_sig = i
        rsi_now, atr_now, sma50 = ind["rsi"][i], ind["atr"][i], ind["sma50"][i]
        if rsi_now is None or atr_now is None or regime is None:
            continue
        direction = gen_direction(mode, regime, rsi_now, closes[i], sma50, rsi_buy, rsi_sell)
        if direction is None:
            continue
        sign = 1 if direction == "achat" else -1
        risk = stop_mult * atr_now
        if risk <= 0:
            continue
        open_trade = {
            "actif": "", "direction": direction, "sign": sign,
            "entree": closes[i], "risk": risk, "regime_entree": regime,
            "ouvert_le": candles[i]["time"], "entry_bar": i,
            "phase": "full", "stop_r": -1.0, "pnl": 0.0, "statut": None,
        }
    # trade ouvert en fin de période: ignoré (non clôturé)
    return trades


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "net": 0.0, "win_pct": None, "pf": None}
    net = sum(t["pnl_net"] for t in trades)
    wins = [t for t in trades if t["pnl_net"] > 0]
    gains = sum(t["pnl_net"] for t in wins)
    pertes = -sum(t["pnl_net"] for t in trades if t["pnl_net"] < 0)
    return {
        "n": len(trades),
        "net": round(net, 2),
        "win_pct": round(len(wins) / len(trades) * 100, 1),
        "pf": round(gains / pertes, 2) if pertes > 0 else None,
    }


# ---------------------------------------------------------------- sweep

def main() -> None:
    grid = list(itertools.product(
        [15, 60],                       # intervalle (minutes)
        [(35, 65), (30, 70), (25, 75)], # seuils RSI
        ["actuel", "range_seul", "adaptatif"],
        [1.5, 2.0],                     # stop en multiples d'ATR
    ))
    print(f"{len(grid)} configurations x {len(ASSETS)} actifs — friction {FRICTION}R, cooldown {COOLDOWN_MINUTES}min")
    print("Préparation des données (résampling + indicateurs)...")

    data: dict[tuple[str, int], tuple[list[dict], dict]] = {}
    for asset in ASSETS:
        raw = load_5min(asset)
        for minutes in (15, 60):
            candles = resample(raw, minutes)
            data[(asset, minutes)] = (candles, precompute(candles))
            print(f"  {asset} {minutes}min: {len(candles)} bougies", flush=True)

    results = []
    for minutes, (rsi_buy, rsi_sell), mode, stop_mult in grid:
        agg_is, agg_oos, per_asset = [], [], {}
        for asset in ASSETS:
            candles, ind = data[(asset, minutes)]
            trades = simulate(candles, ind, mode, rsi_buy, rsi_sell, stop_mult, minutes)
            t_is = [t for t in trades if t["ouvert_le"] < CUTOFF]
            t_oos = [t for t in trades if t["ouvert_le"] >= CUTOFF]
            agg_is.extend(t_is)
            agg_oos.extend(t_oos)
            per_asset[asset] = {"is": metrics(t_is), "oos": metrics(t_oos)}
        m_is, m_oos = metrics(agg_is), metrics(agg_oos)
        results.append({
            "config": {"intervalle": f"{minutes}min", "rsi": f"{rsi_buy}/{rsi_sell}",
                       "mode": mode, "stop_atr": stop_mult},
            "in_sample": m_is, "out_of_sample": m_oos,
            "total_net": round(m_is["net"] + m_oos["net"], 2),
            "robuste": m_is["net"] > 0 and m_oos["net"] > 0 and m_oos["n"] >= 30,
            "par_actif": per_asset,
        })

    results.sort(key=lambda r: (r["robuste"], r["out_of_sample"]["net"]), reverse=True)

    print(f"\n{'Config':<42} {'IS net':>8} {'IS n':>6} {'OOS net':>8} {'OOS n':>6} {'OOS PF':>7} {'Robuste':>8}")
    print("-" * 92)
    for r in results[:20]:
        c = r["config"]
        label = f"{c['intervalle']} rsi{c['rsi']} {c['mode']} stop{c['stop_atr']}"
        print(f"{label:<42} {r['in_sample']['net']:>7}R {r['in_sample']['n']:>6} "
              f"{r['out_of_sample']['net']:>7}R {r['out_of_sample']['n']:>6} "
              f"{str(r['out_of_sample']['pf']):>7} {'OUI' if r['robuste'] else 'non':>8}")

    robustes = [r for r in results if r["robuste"]]
    print(f"\nConfigurations robustes (positives en optimisation ET en validation): {len(robustes)}/{len(results)}")

    out = Path(__file__).parent / "sweep_report.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Rapport complet: {out}")


if __name__ == "__main__":
    main()
