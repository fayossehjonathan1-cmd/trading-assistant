"""Génération de signaux de trading via l'API Claude (sortie JSON structurée garantie)."""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from .regime import strategy_for_regime

logger = logging.getLogger(__name__)


class SignalIA(BaseModel):
    """Schéma de sortie imposé à Claude via structured outputs."""
    direction: str = Field(description="'achat', 'vente' ou 'neutre'")
    strategie: str = Field(description="Stratégie appliquée, adaptée au régime détecté")
    entree: float = Field(description="Prix d'entrée proposé (prix actuel si neutre)")
    sl: float = Field(description="Stop loss")
    tp1: float = Field(description="Premier objectif de profit")
    tp2: float = Field(description="Second objectif de profit")
    invalidation: float = Field(description="Niveau structurel qui invaliderait le scénario s'il est cassé")
    confiance: int = Field(description="Confiance de 0 à 100")
    analyse: str = Field(description="Raisonnement complet en français: technique, macro/news, gestion du risque")


SYSTEM_PROMPT = """Tu es un analyste de trading professionnel spécialisé forex, or et crypto.
Tu produis des signaux disciplinés basés sur la confluence entre analyse technique et contexte macro.

Cadre stratégique (validé par backtest 6 mois sur bougies 1h — voir backend/sweep2.py):
seul le suivi de tendance par cassure de canal a montré un edge (PF 1.33 hors échantillon);
le retour à la moyenne n'en a montré aucun. Tu opères donc UNIQUEMENT ce cadre.

Règles strictes:
- direction 'achat' ou 'vente' SEULEMENT si le prix vient de casser le canal Donchian
  fourni dans les données (clôture au-dessus du haut du canal => achat; en-dessous du
  bas => vente) dans un régime de tendance, ET si le momentum/les news ne
  contredisent pas la cassure. Sinon: direction='neutre' avec confiance < 40.
- SL à environ 2x ATR du prix d'entrée.
- Le ratio risque/rendement du TP1 doit être >= 1.5, celui du TP2 >= 3.
- Le niveau d'invalidation est le niveau structurel dont la cassure annulerait le scénario.
- Les niveaux doivent être cohérents avec le prix actuel et l'ATR.
- L'analyse est rédigée en français, concise mais complète (technique, macro/news, risque)."""


def build_user_prompt(snapshot: dict, regime: str, news: list[dict]) -> str:
    news_txt = "\n".join(
        f"- [{n.get('sentiment', 'n/a')}] {n['titre']} — {n.get('resume', '')}" for n in news[:8]
    ) or "- Aucune actualité notable sur les 4 dernières heures."
    candles = "\n".join(
        f"  {c['time']}: O={c['open']} H={c['high']} L={c['low']} C={c['close']}" for c in snapshot.get("candles", [])
    )
    intervalle = snapshot.get("intervalle", "5min")
    return f"""Analyse l'actif {snapshot['actif']} et génère un signal de trading.

## Données techniques (bougies {intervalle})
- Prix actuel: {snapshot['prix']}
- RSI(14): {snapshot['rsi']}
- ATR(14): {snapshot['atr']} (moyenne récente: {snapshot['atr_moyen']})
- ADX(14): {snapshot['adx']}
- Variation sur 12 bougies: {snapshot.get('variation_pct')}%
- Canal Donchian {snapshot.get('donchian_periode', 10)} bougies (bougie courante exclue): haut {snapshot['plus_haut_recent']} / bas {snapshot['plus_bas_recent']}
- Dernières bougies:
{candles}

## Régime de marché détecté
{regime} — stratégie recommandée: {strategy_for_regime(regime)}

## Actualités des dernières heures (score de sentiment entre -1 et 1)
{news_txt}

Génère le signal en respectant strictement le schéma JSON demandé."""


class ClaudeAnalyst:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def analyze(self, snapshot: dict, regime: str, news: list[dict]) -> SignalIA | None:
        import anthropic
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(snapshot, regime, news)}],
                output_format=SignalIA,
            )
            if response.stop_reason == "refusal":
                logger.warning("Claude a refusé l'analyse pour %s", snapshot["actif"])
                return None
            return response.parsed_output
        except anthropic.RateLimitError:
            logger.warning("Claude rate-limité — cycle sauté pour %s", snapshot["actif"])
            return None
        except anthropic.APIStatusError as exc:
            logger.error("Erreur API Claude (%s): %s", exc.status_code, exc.message)
            return None
        except anthropic.APIConnectionError:
            logger.error("Connexion API Claude impossible")
            return None
        except Exception:
            logger.exception("Erreur inattendue lors de l'analyse Claude")
            return None


class MockAnalyst:
    """Analyste de repli: cassure Donchian en régime tendance — la règle mécanique
    validée par backtest 6 mois (backend/sweep2.py, sweep3.py). Utilisé sans clé Anthropic."""

    def analyze(self, snapshot: dict, regime: str, news: list[dict]) -> SignalIA | None:
        prix = snapshot["prix"]
        atr = snapshot["atr"] or prix * 0.002
        adx = snapshot.get("adx") or 0.0
        ch_high = snapshot.get("plus_haut_recent")
        ch_low = snapshot.get("plus_bas_recent")
        periode = snapshot.get("donchian_periode", 10)

        direction = "neutre"
        if regime == "tendance" and ch_high is not None and ch_low is not None:
            if prix > ch_high:
                direction = "achat"
            elif prix < ch_low:
                direction = "vente"

        sign = 1 if direction == "achat" else -1
        risk = 2.0 * atr  # stop 2xATR (config validée)
        if direction == "neutre":
            analyse = (
                f"[MOCK] {snapshot['actif']} en régime {regime}: pas de cassure du canal "
                f"Donchian({periode}) [{ch_low} ; {ch_high}] — aucun trade (règle backtest: "
                f"cassure en tendance uniquement)."
            )
            confiance = 25
        else:
            analyse = (
                f"[MOCK] {snapshot['actif']}: cassure {'haussière' if sign > 0 else 'baissière'} du canal "
                f"Donchian({periode}) [{ch_low} ; {ch_high}] en régime tendance (ADX={adx}). "
                f"SL=2xATR, TP1=1.5R, TP2=3R — configuration validée par backtest 6 mois."
            )
            confiance = min(80, int(50 + max(adx - 25, 0)))
        return SignalIA(
            direction=direction,
            strategie=strategy_for_regime(regime),
            entree=round(prix, 5),
            sl=round(prix - sign * risk, 5),
            tp1=round(prix + sign * risk * 1.5, 5),
            tp2=round(prix + sign * risk * 3.0, 5),
            invalidation=round(prix - sign * risk * 1.2, 5),
            confiance=confiance,
            analyse=analyse,
        )
