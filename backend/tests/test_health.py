from collections.abc import Callable

from fastapi.testclient import TestClient

FRONTEND_ORIGIN = "http://localhost:5173"


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


def test_health_reports_ai_unavailable_without_api_key(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.json()["ai_available"] is False


def test_health_reports_ai_available_with_api_key(
    client_factory: Callable[..., TestClient],
) -> None:
    client = client_factory(groq_api_key="test-key")

    response = client.get("/api/health")

    assert response.json()["ai_available"] is True


def test_health_treats_blank_api_key_as_unavailable(
    client_factory: Callable[..., TestClient],
) -> None:
    # Pusta linia "GROQ_API_KEY=" w .env daje pusty string, a nie None.
    client = client_factory(groq_api_key="   ")

    response = client.get("/api/health")

    assert response.json()["ai_available"] is False


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": FRONTEND_ORIGIN})

    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://evil.example.com"})

    # Serwer odpowiada, ale bez nagłówka CORS — przeglądarka zablokuje odczyt odpowiedzi.
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_for_patch_from_frontend(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
