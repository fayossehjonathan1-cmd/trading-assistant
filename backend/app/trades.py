"""Suivi des trades ouverts : TP/SL, Break-Even à 1R, invalidation structurelle ou de régime."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .db import Store

logger = logging.getLogger(__name__)

CLOSED = {"tp2_touche", "sl_touche", "invalide"}

LABELS = {
    "en_cours": "En cours",
    "tp1_touche": "TP1 touché",
    "tp2_touche": "TP2 touché",
    "sl_touche": "SL touché",
    "invalide": "Invalidé",
    "be_recommande": "BE recommandé",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pnl_r(direction: str, entree: float, sl: float, prix: float) -> float:
    """P&L exprimé en multiples du risque initial (R)."""
    risk = abs(entree - sl)
    if risk == 0:
        return 0.0
    move = (prix - entree) if direction == "achat" else (entree - prix)
    return round(move / risk, 3)


def check_trade(trade: dict, signal: dict, prix: float, regime: str) -> tuple[str | None, dict]:
    """Évalue un trade ouvert. Retourne (nouveau_statut ou None, champs à mettre à jour)."""
    direction = signal["direction"]
    entree, sl = float(signal["entree"]), float(signal["sl"])
    tp1, tp2 = float(signal["tp1"]), float(signal["tp2"])
    invalidation = float(signal.get("invalidation") or 0) or None
    is_buy = direction == "achat"

    pnl = _pnl_r(direction, entree, sl, prix)
    fields: dict = {"prix_actuel": prix, "pnl_estime": pnl}
    statut = trade.get("statut", "en_cours")
    new_statut: str | None = None

    def hit_up(level: float) -> bool:
        return prix >= level if is_buy else prix <= level

    def hit_down(level: float) -> bool:
        return prix <= level if is_buy else prix >= level

    if hit_down(sl):
        new_statut = "sl_touche"
    elif hit_up(tp2):
        new_statut = "tp2_touche"
    elif invalidation and hit_down(invalidation):
        new_statut = "invalide"
    elif regime == "volatile" and signal.get("regime") not in ("volatile", None) and statut == "en_cours":
        # changement radical de régime => le scénario d'origine n'est plus valable
        new_statut = "invalide"
    elif hit_up(tp1) and statut in ("en_cours", "be_recommande"):
        new_statut = "tp1_touche"
    elif pnl >= 1.0 and not trade.get("be_recommande") and statut == "en_cours":
        new_statut = "be_recommande"
        fields["be_recommande"] = True

    if new_statut in CLOSED:
        fields["closed_at"] = _now()
    if new_statut:
        fields["statut"] = new_statut
    return new_statut, fields


class TradeTracker:
    def __init__(self, store: Store, notifier):
        self.store = store
        self.notifier = notifier

    def process_open_trades(self, prices: dict[str, float], regimes: dict[str, str]) -> list[dict]:
        """Vérifie chaque trade ouvert; retourne la liste des transitions (pour le circuit breaker)."""
        transitions = []
        for trade in self.store.get_open_trades():
            signal = self.store.get_signal(trade["signal_id"])
            if not signal:
                continue
            actif = signal["actif"]
            prix = prices.get(actif)
            if prix is None:
                continue  # données de marché indisponibles ce cycle, on réévaluera au suivant
            new_statut, fields = check_trade(trade, signal, prix, regimes.get(actif, "transition"))
            try:
                self.store.update_trade(trade["id"], fields)
            except Exception:
                logger.exception("Mise à jour du trade %s échouée", trade["id"])
                continue
            if new_statut:
                transitions.append({"trade": trade, "signal": signal, "statut": new_statut})
                self.store.insert_event({
                    "actif": actif,
                    "type": f"trade_{new_statut}",
                    "impact": "haute" if new_statut in CLOSED else "moyenne",
                    "details": f"Trade #{trade['id']} ({signal['direction']} @ {signal['entree']}) -> {LABELS[new_statut]}",
                })
                self.notifier.send(
                    f"🔔 {actif} — {LABELS[new_statut]}\n"
                    f"Direction: {signal['direction']} | Entrée: {signal['entree']} | Prix: {prix}\n"
                    f"P&L estimé: {fields.get('pnl_estime')}R"
                )
        return transitions
