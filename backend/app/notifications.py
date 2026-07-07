"""Notifications Telegram (webhook Bot API) avec repli silencieux en mode mock."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._client = httpx.Client(timeout=10)

    def send(self, text: str) -> None:
        for attempt in range(2):
            try:
                resp = self._client.post(self._url, json={"chat_id": self._chat_id, "text": text})
                if resp.status_code == 200:
                    return
                logger.warning("Telegram HTTP %s: %s", resp.status_code, resp.text[:200])
            except Exception as exc:
                logger.warning("Envoi Telegram échoué (tentative %d/2): %s", attempt + 1, exc)
        logger.error("Notification Telegram abandonnée: %s", text[:80])


class NoopNotifier:
    """Journalise au lieu d'envoyer — utilisé quand Telegram n'est pas configuré."""

    def send(self, text: str) -> None:
        logger.info("[NOTIFICATION] %s", text.replace("\n", " | "))
