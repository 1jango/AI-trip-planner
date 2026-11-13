"""Wspólne fixtures dla testów. Testy nigdy nie czytają prawdziwego .env."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings bez .env, bez klucza API i z bazą w pamięci (o ile nie podano inaczej)."""
    # "sqlite://" = baza in-memory: każdy test dostaje świeżą, pustą bazę i nie tworzy plików.
    values: dict[str, object] = {"groq_api_key": None, "database_url": "sqlite://"}
    values.update(overrides)
    # _env_file=None wyłącza czytanie .env — testy są powtarzalne na każdym komputerze.
    return Settings(_env_file=None, **values)


@pytest.fixture
def client_factory() -> Iterator[Callable[..., TestClient]]:
    """Zwraca funkcję tworzącą TestClient z wybranymi ustawieniami."""
    created_clients: list[TestClient] = []

    def factory(**overrides: object) -> TestClient:
        settings = make_settings(**overrides)
        app = create_app(settings)
        # Podmieniamy zależność: endpointy dostaną nasze Settings zamiast tych z .env.
        app.dependency_overrides[get_settings] = lambda: settings
        test_client = TestClient(app)
        # __enter__ uruchamia lifespan (tworzenie tabel). Bez tego — jak przy zwykłym
        # TestClient(app) bez "with" — testy dostałyby błąd "no such table".
        test_client.__enter__()
        created_clients.append(test_client)
        return test_client

    yield factory

    for test_client in created_clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(client_factory: Callable[..., TestClient]) -> TestClient:
    """Domyślny klient: aplikacja bez klucza AI."""
    return client_factory()
