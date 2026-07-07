"""API FastAPI + scheduler APScheduler (cycle d'analyse toutes les N minutes)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .engine import AnalysisEngine
from .trades import LABELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

engine = AnalysisEngine(settings)
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(engine.run_cycle, "interval", minutes=settings.analysis_interval_minutes,
                      id="analysis_cycle", coalesce=True, max_instances=1)
    scheduler.start()
    # Premier cycle immédiat pour peupler le dashboard
    try:
        engine.run_cycle()
    except Exception:
        logger.exception("Cycle initial échoué")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Trading Assistant IA", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": {
            "marche": "mock" if settings.use_mock_market else "twelvedata",
            "news": "mock" if settings.use_mock_news else "marketaux",
            "ia": "mock" if settings.use_mock_claude else settings.claude_model,
            "stockage": "memoire" if settings.use_memory_store else "supabase",
            "notifications": "log" if settings.use_noop_notifier else "telegram",
        },
        "dernier_cycle": engine.last_cycle_at,
        "circuit_breaker": {"actif": engine.throttled, "pertes_consecutives": engine.consecutive_losses},
    }


@app.get("/api/dashboard")
def dashboard():
    latest_signals = engine.store.latest_signal_per_asset()
    open_trades = engine.store.get_open_trades()
    trades_by_signal = {t["signal_id"]: t for t in open_trades}
    assets = []
    for actif in settings.symbols:
        snapshot = engine.last_snapshots.get(actif)
        signal = latest_signals.get(actif)
        trade = trades_by_signal.get(signal["id"]) if signal else None
        assets.append({
            "actif": actif,
            "prix": snapshot["prix"] if snapshot else None,
            "rsi": snapshot["rsi"] if snapshot else None,
            "adx": snapshot["adx"] if snapshot else None,
            "atr": snapshot["atr"] if snapshot else None,
            "regime": engine.last_regimes.get(actif),
            "signal": signal,
            "trade_ouvert": trade,
        })
    return {"actifs": assets, "dernier_cycle": engine.last_cycle_at,
            "circuit_breaker": engine.throttled}


@app.get("/api/signals")
def signals(actif: str | None = None, limit: int = 50):
    return engine.store.get_signals(actif=actif, limit=min(limit, 200))


@app.get("/api/trades")
def trades(statut: str = "all", limit: int = 100):
    if statut == "open":
        rows = engine.store.get_open_trades()
    else:
        rows = engine.store.get_trades(limit=min(limit, 200))
    signals_cache = {}
    for t in rows:
        sid = t["signal_id"]
        if sid not in signals_cache:
            signals_cache[sid] = engine.store.get_signal(sid)
        t["signal"] = signals_cache[sid]
        t["statut_label"] = LABELS.get(t.get("statut", ""), t.get("statut"))
    return rows


@app.get("/api/history")
def history():
    all_trades = engine.store.get_trades(limit=200)
    closed = [t for t in all_trades if t.get("statut") in ("tp2_touche", "sl_touche", "invalide")
              or (t.get("statut") == "tp1_touche" and t.get("closed_at"))]
    wins = [t for t in closed if t["statut"] in ("tp1_touche", "tp2_touche")]

    def _agg(rows: list[dict], key_fn) -> dict:
        out: dict[str, dict] = {}
        for t in rows:
            sig = engine.store.get_signal(t["signal_id"]) or {}
            k = key_fn(t, sig)
            bucket = out.setdefault(k, {"total": 0, "gagnes": 0, "pnl_total": 0.0})
            bucket["total"] += 1
            bucket["gagnes"] += 1 if t["statut"] in ("tp1_touche", "tp2_touche") else 0
            bucket["pnl_total"] = round(bucket["pnl_total"] + (t.get("pnl_estime") or 0), 3)
        return out

    return {
        "total_trades": len(closed),
        "taux_reussite": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "pnl_total_r": round(sum(t.get("pnl_estime") or 0 for t in closed), 3),
        "par_actif": _agg(closed, lambda t, s: s.get("actif", "?")),
        "par_regime": _agg(closed, lambda t, s: s.get("regime", "?")),
        "trades": trades(statut="all"),
    }


@app.get("/api/events")
def events(limit: int = 50):
    return engine.store.get_events(limit=min(limit, 200))


@app.post("/api/cycle/run")
def run_cycle_now():
    try:
        return engine.run_cycle()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/circuit-breaker/reset")
def reset_breaker():
    engine.reset_circuit_breaker()
    return {"status": "reset"}
