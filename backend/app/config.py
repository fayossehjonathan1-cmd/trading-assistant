"""Configuration centralisée — toutes les clés viennent des variables d'environnement (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Clés API externes (vides => mode mock automatique pour ce service)
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    twelvedata_api_key: str = field(default_factory=lambda: os.environ.get("TWELVEDATA_API_KEY", ""))
    marketaux_api_token: str = field(default_factory=lambda: os.environ.get("MARKETAUX_API_TOKEN", ""))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))

    # Supabase (vide => stockage en mémoire pour le dev local)
    supabase_url: str = field(default_factory=lambda: os.environ.get("SUPABASE_URL", "").rstrip("/"))
    supabase_service_role_key: str = field(default_factory=lambda: os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))

    # Moteur d'analyse
    claude_model: str = field(default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-opus-4-8"))
    analysis_interval_minutes: int = field(default_factory=lambda: int(os.environ.get("ANALYSIS_INTERVAL_MINUTES", "5")))
    signal_cooldown_minutes: int = field(default_factory=lambda: int(os.environ.get("SIGNAL_COOLDOWN_MINUTES", "60")))
    # Config validée par backtest 6 mois (voir backend/sweep2.py et sweep3.py):
    # bougies 1h, cassure Donchian 10, signaux uniquement en régime tendance
    candle_interval: str = field(default_factory=lambda: os.environ.get("CANDLE_INTERVAL", "1h"))
    trade_regimes: str = field(default_factory=lambda: os.environ.get("TRADE_REGIMES", "tendance"))
    donchian_period: int = field(default_factory=lambda: int(os.environ.get("DONCHIAN_PERIOD", "10")))
    news_lookback_hours: int = field(default_factory=lambda: int(os.environ.get("NEWS_LOOKBACK_HOURS", "4")))
    max_consecutive_losses: int = field(default_factory=lambda: int(os.environ.get("MAX_CONSECUTIVE_LOSSES", "3")))

    # Force le mode mock même si des clés sont présentes
    mock_mode: bool = field(default_factory=lambda: _bool("MOCK_MODE", False))

    cors_origins: str = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*"))

    # Actifs suivis : nom d'affichage -> symbole Twelve Data
    symbols: dict[str, str] = field(default_factory=lambda: {
        "XAUUSD": "XAU/USD",
        "EURUSD": "EUR/USD",
        "BTCUSD": "BTC/USD",
    })

    @property
    def trade_regimes_set(self) -> set[str]:
        if self.trade_regimes.strip().lower() == "tous":
            return {"tendance", "range", "volatile", "transition"}
        return {r.strip() for r in self.trade_regimes.split(",") if r.strip()}

    @property
    def use_mock_market(self) -> bool:
        return self.mock_mode or not self.twelvedata_api_key

    @property
    def use_mock_news(self) -> bool:
        return self.mock_mode or not self.marketaux_api_token

    @property
    def use_mock_claude(self) -> bool:
        return self.mock_mode or not self.anthropic_api_key

    @property
    def use_memory_store(self) -> bool:
        return self.mock_mode or not (self.supabase_url and self.supabase_service_role_key)

    @property
    def use_noop_notifier(self) -> bool:
        return self.mock_mode or not (self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
