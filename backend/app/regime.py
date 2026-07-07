"""Détection du régime de marché à partir des indicateurs techniques."""
from __future__ import annotations

VOLATILE_ATR_RATIO = 1.8  # ATR courant > 1.8x sa moyenne récente => marché volatil


def detect_regime(adx: float | None, atr: float | None, atr_moyen: float | None) -> str:
    """Retourne 'volatile', 'tendance', 'range' ou 'transition' (ADX entre 20 et 25)."""
    if atr and atr_moyen and atr / atr_moyen > VOLATILE_ATR_RATIO:
        return "volatile"
    if adx is None:
        return "transition"
    if adx > 25:
        return "tendance"
    if adx < 20:
        return "range"
    return "transition"


def strategy_for_regime(regime: str) -> str:
    return {
        "tendance": "cassure de canal Donchian dans le sens de la tendance (validée par backtest)",
        "range": "aucun trade (pas d'edge démontré en backtest)",
        "volatile": "aucun trade (invalidation des positions ouvertes)",
        "transition": "attentiste (confirmation requise)",
    }.get(regime, "attentiste")
