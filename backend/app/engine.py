"""Orchestration d'un cycle d'analyse complet + circuit breaker sur pertes consécutives."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .claude_analyst import ClaudeAnalyst, MockAnalyst, SignalIA
from .config import Settings
from .db import MemoryStore, Store, SupabaseStore
from .market_data import MockMarketData, TwelveDataClient
from .news import MarketauxClient, MockNews
from .notifications import NoopNotifier, TelegramNotifier
from .regime import detect_regime
from .trades import TradeTracker

logger = logging.getLogger(__name__)


class AnalysisEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store: Store = MemoryStore() if settings.use_memory_store else SupabaseStore(
            settings.supabase_url, settings.supabase_service_role_key)
        self.market = MockMarketData(settings.donchian_period) if settings.use_mock_market else TwelveDataClient(
            settings.twelvedata_api_key, settings.candle_interval, settings.donchian_period)
        self.news = MockNews() if settings.use_mock_news else MarketauxClient(settings.marketaux_api_token)
        self.analyst = MockAnalyst() if settings.use_mock_claude else ClaudeAnalyst(
            settings.anthropic_api_key, settings.claude_model)
        self.notifier = NoopNotifier() if settings.use_noop_notifier else TelegramNotifier(
            settings.telegram_bot_token, settings.telegram_chat_id)
        self.tracker = TradeTracker(self.store, self.notifier)

        self.consecutive_losses = 0
        self.throttled = False
        self.last_cycle_at: str | None = None
        self.last_snapshots: dict[str, dict] = {}
        self.last_regimes: dict[str, str] = {}

        logger.info(
            "Moteur initialisé — marché:%s news:%s claude:%s store:%s notif:%s",
            "mock" if settings.use_mock_market else "twelvedata",
            "mock" if settings.use_mock_news else "marketaux",
            "mock" if settings.use_mock_claude else settings.claude_model,
            "memoire" if settings.use_memory_store else "supabase",
            "log" if settings.use_noop_notifier else "telegram",
        )

    # ------------------------------------------------------------------ cycle

    def run_cycle(self) -> dict:
        """Un cycle complet: prix -> régimes -> suivi des trades -> nouveaux signaux."""
        report = {"snapshots": 0, "signals": 0, "transitions": 0, "errors": []}

        snapshots: dict[str, dict] = {}
        for display, td_symbol in self.settings.symbols.items():
            try:
                snapshots[display] = self.market.get_snapshot(display, td_symbol)
                snapshots[display]["intervalle"] = self.settings.candle_interval
                report["snapshots"] += 1
            except Exception as exc:
                logger.error("Prix indisponibles pour %s: %s", display, exc)
                report["errors"].append(f"{display}: {exc}")

        regimes = {
            a: detect_regime(s["adx"], s["atr"], s["atr_moyen"]) for a, s in snapshots.items()
        }
        prices = {a: s["prix"] for a, s in snapshots.items()}
        self.last_snapshots = snapshots
        self.last_regimes = regimes

        # 1. Suivi des trades ouverts (toujours, même si le circuit breaker est actif)
        try:
            transitions = self.tracker.process_open_trades(prices, regimes)
            report["transitions"] = len(transitions)
            self._update_circuit_breaker(transitions)
        except Exception:
            logger.exception("Erreur pendant le suivi des trades")
            report["errors"].append("suivi trades")

        # 2. Génération de nouveaux signaux
        if not self.throttled:
            try:
                news = self.news.get_recent_news(hours=self.settings.news_lookback_hours)
            except Exception:
                logger.exception("Récupération des news échouée")
                news = []
            open_assets = self._open_assets()
            allowed_regimes = self.settings.trade_regimes_set
            for actif, snapshot in snapshots.items():
                # config validée par backtest: pas de signaux hors des régimes autorisés
                if regimes[actif] not in allowed_regimes:
                    continue
                if actif in open_assets or not self._cooldown_elapsed(actif):
                    continue
                try:
                    if self._generate_signal(actif, snapshot, regimes[actif], news):
                        report["signals"] += 1
                except Exception:
                    logger.exception("Génération de signal échouée pour %s", actif)
                    report["errors"].append(f"signal {actif}")

        self.last_cycle_at = datetime.now(timezone.utc).isoformat()
        report["throttled"] = self.throttled
        logger.info("Cycle terminé: %s", report)
        return report

    # ------------------------------------------------------------- internals

    def _open_assets(self) -> set[str]:
        assets = set()
        for trade in self.store.get_open_trades():
            signal = self.store.get_signal(trade["signal_id"])
            if signal:
                assets.add(signal["actif"])
        return assets

    def _cooldown_elapsed(self, actif: str) -> bool:
        latest = self.store.latest_signal_per_asset().get(actif)
        if not latest:
            return True
        try:
            created = datetime.fromisoformat(str(latest["created_at"]).replace("Z", "+00:00"))
        except ValueError:
            return True
        return datetime.now(timezone.utc) - created >= timedelta(minutes=self.settings.signal_cooldown_minutes)

    def _generate_signal(self, actif: str, snapshot: dict, regime: str, news: list[dict]) -> bool:
        result: SignalIA | None = self.analyst.analyze(snapshot, regime, news)
        if result is None:
            return False
        signal_row = self.store.insert_signal({
            "actif": actif,
            "regime": regime,
            "strategie": result.strategie,
            "direction": result.direction,
            "entree": result.entree,
            "sl": result.sl,
            "tp1": result.tp1,
            "tp2": result.tp2,
            "invalidation": result.invalidation,
            "confiance": result.confiance,
            "analyse": result.analyse,
        })
        self.store.insert_event({
            "actif": actif, "type": "signal", "impact": "haute" if result.confiance >= 60 else "moyenne",
            "details": f"Signal {result.direction} ({result.confiance}%) en régime {regime}",
        })
        if result.direction in ("achat", "vente") and result.confiance >= 40:
            self.store.insert_trade({
                "signal_id": signal_row["id"],
                "actif": actif,
                "direction": result.direction,
                "statut": "en_cours",
                "prix_actuel": snapshot["prix"],
                "pnl_estime": 0.0,
                "be_recommande": False,
            })
            self.notifier.send(
                f"📈 Nouveau signal {actif} — {result.direction.upper()} ({result.confiance}%)\n"
                f"Régime: {regime} | Entrée: {result.entree} | SL: {result.sl}\n"
                f"TP1: {result.tp1} | TP2: {result.tp2}\n{result.analyse[:300]}"
            )
        return True

    def _update_circuit_breaker(self, transitions: list[dict]) -> None:
        for tr in transitions:
            if tr["statut"] == "sl_touche":
                self.consecutive_losses += 1
            elif tr["statut"] in ("tp1_touche", "tp2_touche"):
                self.consecutive_losses = 0
        if self.consecutive_losses >= self.settings.max_consecutive_losses and not self.throttled:
            self.throttled = True
            self.notifier.send(
                f"⚠️ Circuit breaker activé: {self.consecutive_losses} SL consécutifs. "
                "Génération de signaux suspendue jusqu'à validation manuelle (POST /api/circuit-breaker/reset)."
            )
            self.store.insert_event({
                "actif": None, "type": "circuit_breaker", "impact": "haute",
                "details": f"{self.consecutive_losses} pertes consécutives — signaux suspendus",
            })

    def reset_circuit_breaker(self) -> None:
        self.consecutive_losses = 0
        self.throttled = False
        self.notifier.send("✅ Circuit breaker réinitialisé — génération de signaux réactivée.")
