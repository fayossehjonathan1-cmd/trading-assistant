"""Second sweep: famille structurellement différente — cassure Donchian en tendance.

Entrée: cassure du plus haut/bas des 20 dernières bougies, uniquement en régime tendance.
Variantes: intervalle 15min/1h, TP (1R/2R) ou (1.5R/3R), filtre session 07-17h UTC
(Londres+NY, appliqué au forex/or seulement — BTC coté 24/7).
Validation in-sample (janv-avril) / out-of-sample (mai-juillet), friction 0.05R.

Usage: python sweep2.py
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from sweep import ASSETS, CUTOFF, FRICTION, WARMUP, load_5min, metrics, precompute, resample

COOLDOWN_MINUTES = 120


def _pos_r(tr: dict, price: float) -> float:
    return tr["sign"] * (price - tr["entree"]) / tr["risk"]


def step_trade(tr: dict, candle: dict, regime: str, bar: int, tp1: float, tp2: float) -> bool:
    """Comme backtest._step_trade mais avec TP paramétrables (en R). Pessimiste: stop d'abord."""
    hi_r = _pos_r(tr, candle["high"])
    lo_r = _pos_r(tr, candle["low"])
    best, worst = max(hi_r, lo_r), min(hi_r, lo_r)

    def close(statut: str) -> bool:
        tr["statut"] = statut
        return True

    if tr["phase"] == "full":
        if worst <= tr["stop_r"]:
            tr["pnl"] += tr["stop_r"]
            return close("sl_touche")
        if regime == "volatile" and tr["regime_entree"] != "volatile":
            tr["pnl"] += _pos_r(tr, candle["close"])
            return close("invalide")
        if best >= tp1:
            tr["pnl"] += 0.5 * tp1
            tr["phase"] = "half"
            tr["stop_r"] = 0.0
            if worst <= 0.0:
                return close("tp1_touche_be")
            if best >= tp2:
                tr["pnl"] += 0.5 * tp2
                return close("tp2_touche")
        return False
    if worst <= tr["stop_r"]:
        tr["pnl"] += 0.5 * tr["stop_r"]
        return close("tp1_touche_be")
    if regime == "volatile" and tr["regime_entree"] != "volatile":
        tr["pnl"] += 0.5 * _pos_r(tr, candle["close"])
        return close("invalide_apres_tp1")
    if best >= tp2:
        tr["pnl"] += 0.5 * tp2
        return close("tp2_touche")
    return False


def in_session(time_str: str) -> bool:
    hour = int(time_str[11:13])
    return 7 <= hour < 17  # Londres + New York (UTC)


def simulate(asset: str, candles: list[dict], ind: dict, minutes: int,
             tp1: float, tp2: float, session_filter: bool, donchian: int = 20) -> list[dict]:
    cooldown_bars = max(1, round(COOLDOWN_MINUTES / minutes))
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    trades: list[dict] = []
    open_trade: dict | None = None
    last_sig = -(10 ** 9)

    for i in range(WARMUP, len(candles)):
        regime = ind["regime"][i]
        if open_trade is not None:
            if step_trade(open_trade, candles[i], regime, i, tp1, tp2):
                open_trade["pnl_net"] = round(open_trade["pnl"] - FRICTION, 4)
                open_trade["ferme_le"] = candles[i]["time"]
                trades.append(open_trade)
                open_trade = None
            continue
        if i - last_sig < cooldown_bars:
            continue
        if regime != "tendance":
            continue
        if session_filter and asset != "BTCUSD" and not in_session(candles[i]["time"]):
            continue
        atr_now = ind["atr"][i]
        if atr_now is None:
            continue
        ch_high = max(highs[i - donchian:i])
        ch_low = min(lows[i - donchian:i])
        direction = "achat" if closes[i] > ch_high else "vente" if closes[i] < ch_low else None
        last_sig = i
        if direction is None:
            continue
        sign = 1 if direction == "achat" else -1
        open_trade = {
            "actif": asset, "direction": direction, "sign": sign,
            "entree": closes[i], "risk": 2.0 * atr_now, "regime_entree": regime,
            "ouvert_le": candles[i]["time"], "entry_bar": i,
            "phase": "full", "stop_r": -1.0, "pnl": 0.0, "statut": None,
        }
    return trades


def main() -> None:
    print("Sweep 2 — cassure Donchian(20) en régime tendance, stop 2xATR, cooldown 2h")
    data = {}
    for asset in ASSETS:
        raw = load_5min(asset)
        for minutes in (15, 60):
            candles = resample(raw, minutes)
            data[(asset, minutes)] = (candles, precompute(candles))
    print("Données prêtes.\n")

    grid = list(itertools.product([15, 60], [(1.0, 2.0), (1.5, 3.0)], [False, True]))
    results = []
    for minutes, (tp1, tp2), session in grid:
        agg_is, agg_oos, per_asset = [], [], {}
        for asset in ASSETS:
            candles, ind = data[(asset, minutes)]
            trades = simulate(asset, candles, ind, minutes, tp1, tp2, session)
            agg_is.extend(t for t in trades if t["ouvert_le"] < CUTOFF)
            agg_oos.extend(t for t in trades if t["ouvert_le"] >= CUTOFF)
            per_asset[asset] = metrics(trades)
        m_is, m_oos = metrics(agg_is), metrics(agg_oos)
        results.append({
            "config": {"intervalle": f"{minutes}min", "tp": f"{tp1}/{tp2}R",
                       "session_7h17h": session},
            "in_sample": m_is, "out_of_sample": m_oos,
            "robuste": m_is["net"] > 0 and m_oos["net"] > 0 and m_oos["n"] >= 30,
            "par_actif": per_asset,
        })

    results.sort(key=lambda r: (r["robuste"], r["out_of_sample"]["net"]), reverse=True)
    print(f"{'Config':<38} {'IS net':>8} {'IS n':>6} {'OOS net':>8} {'OOS n':>6} {'OOS PF':>7} {'Robuste':>8}")
    print("-" * 88)
    for r in results:
        c = r["config"]
        label = f"{c['intervalle']} tp{c['tp']} session={'oui' if c['session_7h17h'] else 'non'}"
        print(f"{label:<38} {r['in_sample']['net']:>7}R {r['in_sample']['n']:>6} "
              f"{r['out_of_sample']['net']:>7}R {r['out_of_sample']['n']:>6} "
              f"{str(r['out_of_sample']['pf']):>7} {'OUI' if r['robuste'] else 'non':>8}")

    robustes = [r for r in results if r["robuste"]]
    print(f"\nConfigurations robustes: {len(robustes)}/{len(results)}")
    out = Path(__file__).parent / "sweep2_report.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Rapport: {out}")


if __name__ == "__main__":
    main()
