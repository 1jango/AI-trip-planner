"""Prosty cache odpowiedzi zewnętrznych API w SQLite.

Po co: Transitous prosi o "mało zapytań". To samo wyszukiwanie wykonane drugi raz
(np. odświeżenie strony) bierzemy z bazy, zamiast znowu pytać serwer.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel

from app.models import utc_now


class ApiCacheEntry(SQLModel, table=True):
    key: str = Field(primary_key=True)  # skrót SHA-256 zapytania
    payload: str  # surowa odpowiedź API jako JSON
    expires_at: datetime


def make_cache_key(path: str, params: dict[str, Any]) -> str:
    """Ten sam endpoint + te same parametry = ten sam klucz, niezależnie od kolejności."""
    # sort_keys=True: {"a": 1, "b": 2} i {"b": 2, "a": 1} dają identyczny tekst.
    canonical = json.dumps({"path": path, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, engine: Engine, clock: Callable[[], datetime] = utc_now) -> None:
        self._engine = engine
        # Zegar wstrzykiwany: w testach podajemy "sztuczny czas", żeby sprawdzić wygasanie
        # bez czekania godzinę.
        self._clock = clock

    def get(self, key: str) -> Any | None:
        """Zwraca zapisaną odpowiedź albo None, gdy jej nie ma lub wygasła."""
        with Session(self._engine) as session:
            entry = session.get(ApiCacheEntry, key)
            if entry is None or entry.expires_at <= self._clock():
                return None
            return json.loads(entry.payload)

    def set(self, key: str, value: Any, ttl: timedelta) -> None:
        with Session(self._engine) as session:
            entry = ApiCacheEntry(
                key=key, payload=json.dumps(value), expires_at=self._clock() + ttl
            )
            # merge = INSERT albo UPDATE, jeśli klucz już istnieje (np. wygasły wpis).
            session.merge(entry)
            session.commit()
