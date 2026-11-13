from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from app.database import create_db_and_tables, create_db_engine
from app.services.cache import ResponseCache, make_cache_key


class FakeClock:
    """Zegar, którym sterujemy ręcznie — test wygasania bez czekania."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    yield engine
    engine.dispose()


def test_cache_key_ignores_param_order() -> None:
    assert make_cache_key("/x", {"a": 1, "b": 2}) == make_cache_key("/x", {"b": 2, "a": 1})


def test_cache_key_differs_for_different_params() -> None:
    assert make_cache_key("/x", {"a": 1}) != make_cache_key("/x", {"a": 2})


def test_missing_key_returns_none(engine: Engine) -> None:
    assert ResponseCache(engine).get("missing") is None


def test_stored_value_is_returned_before_expiry(engine: Engine) -> None:
    clock = FakeClock()
    cache = ResponseCache(engine, clock=clock)
    cache.set("key", {"answer": [1, 2, 3]}, ttl=timedelta(hours=1))

    clock.now += timedelta(minutes=59)

    assert cache.get("key") == {"answer": [1, 2, 3]}


def test_value_expires_after_ttl(engine: Engine) -> None:
    clock = FakeClock()
    cache = ResponseCache(engine, clock=clock)
    cache.set("key", "old", ttl=timedelta(hours=1))

    clock.now += timedelta(hours=1)

    assert cache.get("key") is None


def test_set_overwrites_existing_entry(engine: Engine) -> None:
    cache = ResponseCache(engine)
    cache.set("key", "old", ttl=timedelta(hours=1))

    cache.set("key", "new", ttl=timedelta(hours=1))

    assert cache.get("key") == "new"
