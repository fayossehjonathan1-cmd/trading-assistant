"""Backtest de la stratégie sur bougies réelles Twelve Data.

Rejoue le cadre de trading de l'application sur l'historique réel :
- détection de régime (ADX > 25 tendance, < 20 range, ATR > 1.8x moyenne = volatile)
- signaux de l'analyste à base de règles (le repli utilisé quand Claude est absent)
- SL = 1.5xATR, TP1 = 1R, TP2 = 2R, break-even à +1R,
  invalidation si le régime bascule en volatile
- sortie: 50% à TP1 (stop déplacé au BE), 50% à TP2
- hypothèse pessimiste: si SL et TP sont touchés dans la même bougie, le SL est compté

⚠️ La couche discrétionnaire Claude et le sentiment news ne sont PAS rejoués
(coût API prohibitif, news historiques indisponibles). Les résultats mesurent la
mécanique de la stratégie, pas la valeur ajoutée de l'IA.

Usage:
    python backtest.py --months 6 --interval 5min --friction 0.05
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.claude_analyst import MockAnalyst
from app.config import settings
from app.indicators import adx, atr, atr_series, rsi
from app.regime import detect_regime

CACHE_DIR = Path(__file__).parent / "backtest_cache"
PAGE_SLEEP = 8.5  # plan gratuit Twelve Data: 8 crédits/minute
INTERVAL_MINUTES = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}

# ---------------------------------------------------------------- données

def fetch_history(display: str, td_symbol: str, interval: str, months: int) -> list[dict]:
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / f"{display}_{interval}_{months}m.json"
    if cache.exists():
        candles = json.loads(cache.read_text())
        print(f"  {display}: {len(candles)} bougies (cache)")
        return candles

    start = datetime.now(timezone.utc) - timedelta(days=months * 30.5)
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    client = httpx.Client(timeout=30)
    by_dt: dict[str, dict] = {}
    cursor: str | None = None
    page = 0
    while True:
        page += 1
        params = {
            "symbol": td_symbol, "interval": interval, "outputsize": 5000,
            "apikey": settings.twelvedata_api_key, "timezone": "UTC",
        }
        if cursor:
            params["end_date"] = cursor
        data = None
        for attempt in range(5):
            resp = client.get("https://api.twelvedata.com/time_series", params=params)
            data = resp.json()
            if "values" in data:
                break
            msg = str(data.get("message", data))
            if "credits" in msg or "limit" in msg:  # quota minute atteint (backend live en parallèle)
                print(f"  {display}: quota minute atteint, attente 20s...", flush=True)
                time.sleep(20)
                continue
            raise RuntimeError(f"Twelve Data ({display}, page {page}): {msg}")
        if data is None or "values" not in data:
            raise RuntimeError(f"Twelve Data ({display}, page {page}): quota persistant")
        values = data["values"]  # du plus récent au plus ancien
        for v in values:
            by_dt[v["datetime"]] = {
                "time": v["datetime"],
                "open": float(v["open"]), "high": float(v["high"]),
                "low": float(v["low"]), "close": float(v["close"]),
            }
        oldest = values[-1]["datetime"]
        print(f"  {display}: page {page}, {len(by_dt)} bougies, jusqu'à {oldest}", flush=True)
        if oldest <= start_str or len(values) < 5000:
            break
        cursor = oldest
        time.sleep(PAGE_SLEEP)

    candles = sorted((c for dt, c in by_dt.items() if dt >= start_str), key=lambda c: c["time"])
    cache.write_text(json.dumps(candles))
    print(f"  {display}: {len(candles)} bougies conservées ({candles[0]['time']} -> {candles[-1]['time']})")
    return candles


# ---------------------------------------------------------------- simulation

def simulate_asset(display: str, candles: list[dict], interval: str, friction: float) -> dict:
    analyst = MockAnalyst()
    cooldown_bars = max(1, round(settings.signal_cooldown_minutes / INTERVAL_MINUTES[interval]))
    warmup = 130  # 120 bougies de fenêtre + marge ADX

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    trades: list[dict] = []
    open_trade: dict | None = None
    last_signal_bar = -(10 ** 9)

    for i in range(warmup, len(candles)):
        w0 = i - 119
        w_h, w_l, w_c = highs[w0:i + 1], lows[w0:i + 1], closes[w0:i + 1]
        atr_now = atr(w_h, w_l, w_c)
        adx_now = adx(w_h, w_l, w_c)
        atrs = atr_series(w_h, w_l, w_c)
        atr_avg = sum(atrs[-20:]) / len(atrs[-20:]) if atrs else None
        regime = detect_regime(adx_now, atr_now, atr_avg)

        # --- suivi du trade ouvert
        if open_trade is not None:
            done = _step_trade(open_trade, candles[i], regime, i)
            if done:
                open_trade["pnl_net"] = round(open_trade["pnl"] - friction, 3)
                trades.append(open_trade)
                open_trade = None
            continue

        # --- nouveau signal ?
        if i - last_signal_bar < cooldown_bars:
            continue
        rsi_now = rsi(w_c)
        snapshot = {
            "actif": display, "prix": closes[i], "rsi": rsi_now, "adx": adx_now,
            "atr": atr_now, "atr_moyen": atr_avg, "candles": [],
            "plus_haut_recent": max(w_h[-20:]), "plus_bas_recent": min(w_l[-20:]),
        }
        result = analyst.analyze(snapshot, regime, news=[])
        last_signal_bar = i
        if result is None or result.direction == "neutre" or result.confiance < 40:
            continue
        sign = 1 if result.direction == "achat" else -1
        risk = abs(result.entree - result.sl)
        if risk <= 0:
            continue
        open_trade = {
            "actif": display, "direction": result.direction, "sign": sign,
            "entree": result.entree, "risk": risk, "regime_entree": regime,
            "ouvert_le": candles[i]["time"], "entry_bar": i,
            "phase": "full", "stop_r": -1.0, "pnl": 0.0, "statut": None,
        }

    # trade encore ouvert à la fin: clôture au dernier prix
    if open_trade is not None:
        last_r = _pos_r(open_trade, closes[-1])
        frac = 1.0 if open_trade["phase"] == "full" else 0.5
        open_trade["pnl"] += frac * last_r
        open_trade["statut"] = "ouvert_fin_backtest"
        open_trade["ferme_le"] = candles[-1]["time"]
        open_trade["pnl_net"] = round(open_trade["pnl"] - friction, 3)
        trades.append(open_trade)

    return _report(display, trades)


def _pos_r(tr: dict, price: float) -> float:
    return tr["sign"] * (price - tr["entree"]) / tr["risk"]


def _step_trade(tr: dict, candle: dict, regime: str, bar: int) -> bool:
    """Avance le trade d'une bougie. True si clôturé. Ordre pessimiste: stop avant target."""
    hi_r = _pos_r(tr, candle["high"])
    lo_r = _pos_r(tr, candle["low"])
    best, worst = max(hi_r, lo_r), min(hi_r, lo_r)

    def close(statut: str) -> bool:
        tr["statut"] = statut
        tr["ferme_le"] = candle["time"]
        tr["duree_bougies"] = bar - tr["entry_bar"]
        return True

    if tr["phase"] == "full":
        if worst <= tr["stop_r"]:                     # SL (pessimiste: prioritaire)
            tr["pnl"] += 1.0 * tr["stop_r"]
            return close("sl_touche")
        if regime == "volatile" and tr["regime_entree"] != "volatile":
            tr["pnl"] += 1.0 * _pos_r(tr, candle["close"])   # invalidation régime
            return close("invalide")
        if best >= 1.0:                               # TP1: moitié encaissée, stop au BE
            tr["pnl"] += 0.5 * 1.0
            tr["phase"] = "half"
            tr["stop_r"] = 0.0
            # même bougie, ordre pessimiste: retour au BE avant TP2
            if worst <= 0.0:
                return close("tp1_touche_be")
            if best >= 2.0:
                tr["pnl"] += 0.5 * 2.0
                return close("tp2_touche")
        return False

    # phase "half" (après TP1)
    if worst <= tr["stop_r"]:                         # retour au break-even
        tr["pnl"] += 0.5 * tr["stop_r"]
        return close("tp1_touche_be")
    if regime == "volatile" and tr["regime_entree"] != "volatile":
        tr["pnl"] += 0.5 * _pos_r(tr, candle["close"])
        return close("invalide_apres_tp1")
    if best >= 2.0:
        tr["pnl"] += 0.5 * 2.0
        return close("tp2_touche")
    return False


# ---------------------------------------------------------------- rapport

WIN_STATUSES = {"tp2_touche", "tp1_touche_be", "invalide_apres_tp1"}


def _report(display: str, trades: list[dict]) -> dict:
    closed = [t for t in trades if t["statut"] != "ouvert_fin_backtest"]
    wins = [t for t in closed if t["pnl_net"] > 0]
    gross = sum(t["pnl"] for t in closed)
    net = sum(t["pnl_net"] for t in closed)

    equity = peak = 0.0
    max_dd = 0.0
    for t in closed:
        equity += t["pnl_net"]
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    gains = sum(t["pnl_net"] for t in closed if t["pnl_net"] > 0)
    pertes = -sum(t["pnl_net"] for t in closed if t["pnl_net"] < 0)

    par_regime: dict[str, dict] = {}
    par_statut: dict[str, int] = {}
    for t in closed:
        r = par_regime.setdefault(t["regime_entree"], {"trades": 0, "pnl_net": 0.0})
        r["trades"] += 1
        r["pnl_net"] = round(r["pnl_net"] + t["pnl_net"], 2)
        par_statut[t["statut"]] = par_statut.get(t["statut"], 0) + 1

    return {
        "actif": display,
        "trades_clotures": len(closed),
        "taux_reussite_pct": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "pnl_brut_r": round(gross, 2),
        "pnl_net_r": round(net, 2),
        "moyenne_r_par_trade": round(net / len(closed), 3) if closed else None,
        "profit_factor": round(gains / pertes, 2) if pertes > 0 else None,
        "max_drawdown_r": round(max_dd, 2),
        "par_statut": par_statut,
        "par_regime": par_regime,
        "trades": trades,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--interval", default="5min", choices=list(INTERVAL_MINUTES))
    parser.add_argument("--friction", type=float, default=0.05,
                        help="coût estimé (spread/frais) déduit par trade, en R")
    args = parser.parse_args()

    if not settings.twelvedata_api_key:
        raise SystemExit("TWELVEDATA_API_KEY manquante dans .env")

    print(f"=== Backtest {args.months} mois, bougies {args.interval}, friction {args.friction}R/trade ===")
    print("Téléchargement de l'historique (limite 8 req/min du plan gratuit)...")

    reports = []
    for display, td_symbol in settings.symbols.items():
        candles = fetch_history(display, td_symbol, args.interval, args.months)
        time.sleep(PAGE_SLEEP)
        print(f"Simulation {display} ({len(candles)} bougies)...", flush=True)
        reports.append(simulate_asset(display, candles, args.interval, args.friction))

    print()
    header = f"{'Actif':<8} {'Trades':>6} {'Réussite':>9} {'P&L brut':>9} {'P&L net':>9} {'Moy/trade':>10} {'PF':>6} {'Max DD':>8}"
    print(header)
    print("-" * len(header))
    for r in reports:
        print(f"{r['actif']:<8} {r['trades_clotures']:>6} "
              f"{str(r['taux_reussite_pct']) + '%':>9} "
              f"{r['pnl_brut_r']:>8}R {r['pnl_net_r']:>8}R "
              f"{r['moyenne_r_par_trade']:>9}R "
              f"{str(r['profit_factor']):>6} {r['max_drawdown_r']:>7}R")
    total_net = round(sum(r["pnl_net_r"] for r in reports), 2)
    total_trades = sum(r["trades_clotures"] for r in reports)
    print("-" * len(header))
    print(f"{'TOTAL':<8} {total_trades:>6} {'':>9} {'':>9} {total_net:>8}R")

    print("\nDétail par statut / régime:")
    for r in reports:
        print(f"  {r['actif']}: statuts={r['par_statut']} régimes={r['par_regime']}")

    out = Path(__file__).parent / "backtest_report.json"
    out.write_text(json.dumps(reports, indent=2, ensure_ascii=False))
    print(f"\nRapport complet: {out}")


if __name__ == "__main__":
    main()
