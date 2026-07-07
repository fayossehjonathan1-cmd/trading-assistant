"""Persistance : Supabase (PostgREST via httpx) en production, mémoire en dev/mock.

Les deux implémentations exposent la même interface, le reste du code ne connaît que `Store`.
"""
from __future__ import annotations

import itertools
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("en_cours", "tp1_touche", "be_recommande")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store(Protocol):
    def insert_signal(self, signal: dict) -> dict: ...
    def insert_trade(self, trade: dict) -> dict: ...
    def update_trade(self, trade_id: Any, fields: dict) -> None: ...
    def get_open_trades(self) -> list[dict]: ...
    def get_trades(self, limit: int = 100) -> list[dict]: ...
    def get_signals(self, actif: str | None = None, limit: int = 50) -> list[dict]: ...
    def get_signal(self, signal_id: Any) -> dict | None: ...
    def latest_signal_per_asset(self) -> dict[str, dict]: ...
    def insert_event(self, event: dict) -> None: ...
    def get_events(self, limit: int = 50) -> list[dict]: ...


class SupabaseStore:
    """Accès direct à l'API REST PostgREST de Supabase avec la clé service_role (bypass RLS)."""

    def __init__(self, url: str, service_key: str):
        self._client = httpx.Client(
            base_url=f"{url}/rest/v1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=15,
        )

    def _post(self, table: str, payload: dict) -> dict:
        resp = self._client.post(f"/{table}", json=payload)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else payload

    def _get(self, table: str, params: dict) -> list[dict]:
        resp = self._client.get(f"/{table}", params=params)
        resp.raise_for_status()
        return resp.json()

    def insert_signal(self, signal: dict) -> dict:
        return self._post("signals", signal)

    def insert_trade(self, trade: dict) -> dict:
        return self._post("trades", trade)

    def update_trade(self, trade_id: Any, fields: dict) -> None:
        resp = self._client.patch("/trades", params={"id": f"eq.{trade_id}"}, json=fields)
        resp.raise_for_status()

    def get_open_trades(self) -> list[dict]:
        statuses = ",".join(OPEN_STATUSES)
        return self._get("trades", {"statut": f"in.({statuses})", "order": "opened_at.desc"})

    def get_trades(self, limit: int = 100) -> list[dict]:
        return self._get("trades", {"order": "opened_at.desc", "limit": str(limit)})

    def get_signals(self, actif: str | None = None, limit: int = 50) -> list[dict]:
        params = {"order": "created_at.desc", "limit": str(limit)}
        if actif:
            params["actif"] = f"eq.{actif}"
        return self._get("signals", params)

    def get_signal(self, signal_id: Any) -> dict | None:
        rows = self._get("signals", {"id": f"eq.{signal_id}", "limit": "1"})
        return rows[0] if rows else None

    def latest_signal_per_asset(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for row in self._get("signals", {"order": "created_at.desc", "limit": "60"}):
            result.setdefault(row["actif"], row)
        return result

    def insert_event(self, event: dict) -> None:
        try:
            self._post("market_events", event)
        except Exception:
            logger.exception("Insertion market_event échouée")

    def get_events(self, limit: int = 50) -> list[dict]:
        return self._get("market_events", {"order": "timestamp.desc", "limit": str(limit)})


class MemoryStore:
    """Stockage en mémoire, thread-safe — utilisé quand Supabase n'est pas configuré."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.signals: list[dict] = []
        self.trades: list[dict] = []
        self.events: list[dict] = []

    def insert_signal(self, signal: dict) -> dict:
        with self._lock:
            signal = {**signal, "id": next(self._ids), "created_at": signal.get("created_at") or _now()}
            self.signals.append(signal)
            return signal

    def insert_trade(self, trade: dict) -> dict:
        with self._lock:
            trade = {**trade, "id": next(self._ids), "opened_at": trade.get("opened_at") or _now()}
            self.trades.append(trade)
            return trade

    def update_trade(self, trade_id: Any, fields: dict) -> None:
        with self._lock:
            for t in self.trades:
                if t["id"] == trade_id:
                    t.update(fields)
                    return

    def get_open_trades(self) -> list[dict]:
        with self._lock:
            return [dict(t) for t in self.trades if t.get("statut") in OPEN_STATUSES]

    def get_trades(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return [dict(t) for t in sorted(self.trades, key=lambda t: t["opened_at"], reverse=True)[:limit]]

    def get_signals(self, actif: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = [s for s in self.signals if actif is None or s["actif"] == actif]
            return [dict(s) for s in sorted(rows, key=lambda s: s["created_at"], reverse=True)[:limit]]

    def get_signal(self, signal_id: Any) -> dict | None:
        with self._lock:
            return next((dict(s) for s in self.signals if s["id"] == signal_id), None)

    def latest_signal_per_asset(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for row in self.get_signals(limit=len(self.signals) or 1):
            result.setdefault(row["actif"], row)
        return result

    def insert_event(self, event: dict) -> None:
        with self._lock:
            self.events.append({**event, "id": next(self._ids), "timestamp": event.get("timestamp") or _now()})

    def get_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [dict(e) for e in sorted(self.events, key=lambda e: e["timestamp"], reverse=True)[:limit]]
