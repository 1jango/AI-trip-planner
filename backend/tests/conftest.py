"""Wspólne fixtures dla testów. Testy nigdy nie czytają prawdziwego .env."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def make_settings(**overrides: object) -> Settings:
    """Settings z wartościami domyślnymi, bez .env i bez klucza API (o ile nie podano)."""
    values: dict[str, object] = {"groq_api_key": None}
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
        created_clients.append(test_client)
        return test_client

    yield factory

    for test_client in created_clients:
        test_client.close()


@pytest.fixture
def client(client_factory: Callable[..., TestClient]) -> TestClient:
    """Domyślny klient: aplikacja bez klucza AI."""
    return client_factory()
