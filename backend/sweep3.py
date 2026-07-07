"""Raffinement autour de la config gagnante du sweep2 (Donchian 1h tendance TP1.5/3R).

Fait varier: période Donchian (10/20/55), cooldown (60/120/240 min), régimes admis
(tendance seule ou tendance+transition). Bougies 1h, stop 2xATR, TP 1.5R/3R fixes.
Règle de décision: on ne remplace la config 20/120/tendance que si une variante est
robuste (IS>0 ET OOS>0) et la domine sur les deux périodes.

Usage: python sweep3.py
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from sweep import ASSETS, CUTOFF, FRICTION, WARMUP, load_5min, metrics, precompute, resample
from sweep2 import step_trade

TP1, TP2 = 1.5, 3.0
STOP_MULT = 2.0
MINUTES = 60


def simulate(asset: str, candles: list[dict], ind: dict, donchian: int,
             cooldown_min: int, regimes_ok: tuple[str, ...]) -> list[dict]:
    cooldown_bars = max(1, round(cooldown_min / MINUTES))
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    trades: list[dict] = []
    open_trade: dict | None = None
    last_sig = -(10 ** 9)

    for i in range(max(WARMUP, donchian + 1), len(candles)):
        regime = ind["regime"][i]
        if open_trade is not None:
            if step_trade(open_trade, candles[i], regime, i, TP1, TP2):
                open_trade["pnl_net"] = round(open_trade["pnl"] - FRICTION, 4)
                trades.append(open_trade)
                open_trade = None
            continue
        if i - last_sig < cooldown_bars or regime not in regimes_ok:
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
        open_trade = {
            "actif": asset, "direction": direction, "sign": 1 if direction == "achat" else -1,
            "entree": closes[i], "risk": STOP_MULT * atr_now, "regime_entree": regime,
            "ouvert_le": candles[i]["time"], "entry_bar": i,
            "phase": "full", "stop_r": -1.0, "pnl": 0.0, "statut": None,
        }
    return trades


def main() -> None:
    print("Sweep 3 — raffinement Donchian 1h TP1.5/3R stop2xATR")
    data = {}
    for asset in ASSETS:
        candles = resample(load_5min(asset), MINUTES)
        data[asset] = (candles, precompute(candles))
    print("Données prêtes.\n")

    grid = list(itertools.product(
        [10, 20, 55],
        [60, 120, 240],
        [("tendance",), ("tendance", "transition")],
    ))
    results = []
    for donchian, cooldown, regimes_ok in grid:
        agg_is, agg_oos = [], []
        for asset in ASSETS:
            candles, ind = data[asset]
            trades = simulate(asset, candles, ind, donchian, cooldown, regimes_ok)
            agg_is.extend(t for t in trades if t["ouvert_le"] < CUTOFF)
            agg_oos.extend(t for t in trades if t["ouvert_le"] >= CUTOFF)
        m_is, m_oos = metrics(agg_is), metrics(agg_oos)
        results.append({
            "config": {"donchian": donchian, "cooldown_min": cooldown,
                       "regimes": "+".join(regimes_ok)},
            "in_sample": m_is, "out_of_sample": m_oos,
            "robuste": m_is["net"] > 0 and m_oos["net"] > 0 and m_oos["n"] >= 30,
        })

    results.sort(key=lambda r: (r["robuste"], min(r["in_sample"]["net"], r["out_of_sample"]["net"])), reverse=True)
    print(f"{'Config':<38} {'IS net':>8} {'IS n':>6} {'OOS net':>8} {'OOS n':>6} {'OOS PF':>7} {'Robuste':>8}")
    print("-" * 88)
    for r in results:
        c = r["config"]
        label = f"donchian{c['donchian']} cd{c['cooldown_min']} {c['regimes']}"
        print(f"{label:<38} {r['in_sample']['net']:>7}R {r['in_sample']['n']:>6} "
              f"{r['out_of_sample']['net']:>7}R {r['out_of_sample']['n']:>6} "
              f"{str(r['out_of_sample']['pf']):>7} {'OUI' if r['robuste'] else 'non':>8}")

    out = Path(__file__).parent / "sweep3_report.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()
