"""Actualités financières avec score de sentiment : Marketaux en production, données factices en mock."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)


class MarketauxClient:
    BASE = "https://api.marketaux.com/v1/news/all"

    def __init__(self, api_token: str):
        self.api_token = api_token
        self._client = httpx.Client(timeout=20)

    def get_recent_news(self, hours: int = 4, limit: int = 12) -> list[dict]:
        published_after = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
        for attempt in range(3):
            try:
                resp = self._client.get(self.BASE, params={
                    "api_token": self.api_token,
                    "published_after": published_after,
                    "language": "en",
                    "filter_entities": "true",
                    "industries": "Financial,Financial Services",
                    "limit": limit,
                })
                data = resp.json()
                items = []
                for article in data.get("data", []):
                    sentiments = [e.get("sentiment_score") for e in article.get("entities", [])
                                  if e.get("sentiment_score") is not None]
                    items.append({
                        "titre": article.get("title", ""),
                        "resume": (article.get("description") or "")[:300],
                        "sentiment": round(sum(sentiments) / len(sentiments), 3) if sentiments else None,
                        "publie_le": article.get("published_at", ""),
                        "source": article.get("source", ""),
                    })
                return items
            except Exception as exc:
                logger.warning("Marketaux tentative %d/3 échouée: %s", attempt + 1, exc)
                time.sleep(2 * (attempt + 1))
        logger.error("Marketaux indisponible — cycle sans contexte news")
        return []


class MockNews:
    def get_recent_news(self, hours: int = 4, limit: int = 12) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            {"titre": "Fed officials signal patience on rate cuts amid sticky inflation",
             "resume": "Plusieurs membres de la Fed suggèrent de maintenir les taux inchangés au prochain FOMC.",
             "sentiment": -0.18, "publie_le": now, "source": "mock-news"},
            {"titre": "Gold steadies as dollar retreats from weekly highs",
             "resume": "L'or se stabilise, soutenu par un repli du dollar et des achats de banques centrales.",
             "sentiment": 0.22, "publie_le": now, "source": "mock-news"},
            {"titre": "Bitcoin ETF inflows accelerate for third consecutive session",
             "resume": "Les flux entrants sur les ETF Bitcoin spot s'accélèrent, signal positif pour la demande institutionnelle.",
             "sentiment": 0.35, "publie_le": now, "source": "mock-news"},
        ]
