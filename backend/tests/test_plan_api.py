"""Testy endpointu POST /api/plan: kody odpowiedzi, zależności i zapis wyniku jako podróży."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers.plan import get_intent_parser, get_now, get_route_provider
from app.services.intent_parser import AiUnavailableError, IntentNotUnderstoodError
from app.services.transitous import TransitousClient, TransitousUnavailableError
from tests.plan_fakes import NOW, TRAVEL_DATE, FakeIntentParser, FakeRouteProvider

FORM_REQUEST = {
    "origin": "Gdańsk",
    "destination": "'s-Hertogenbosch",
    "travel_date": TRAVEL_DATE.isoformat(),
    "priority": "fast",
}


def override(
    client: TestClient,
    provider: FakeRouteProvider | None = None,
    parser: FakeIntentParser | None = None,
) -> TestClient:
    """Podmienia zależności endpointu: atrapy klientów i zamrożony zegar."""
    overrides = client.app.dependency_overrides  # type: ignore[attr-defined]
    overrides[get_route_provider] = lambda: provider
    overrides[get_intent_parser] = lambda: parser
    overrides[get_now] = lambda: NOW
    return client


def post_plan(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/api/plan", json=body)


# --- Szczęśliwe ścieżki ---


def test_form_request_returns_ranked_plan(client: TestClient) -> None:
    override(client, provider=FakeRouteProvider())

    response = post_plan(client, FORM_REQUEST)

    assert response.status_code == 200
    plan = response.json()
    assert plan["parsed_by"] == "form"
    assert plan["priority"] == "fast"
    # "fast": szacowany lot (ok. 2,5 h) wyprzedza pociąg (14,5 h).
    assert [option["legs"][0]["mode"] for option in plan["options"]] == ["flight", "train"]
    assert [option["recommended"] for option in plan["options"]] == [True, False]
    assert plan["recommendation"].startswith("Najszybsza opcja")
    assert plan["data_sources_url"] == "https://transitous.org/sources/"


def test_query_request_uses_ai_parser(client: TestClient) -> None:
    parser = FakeIntentParser()
    override(client, provider=FakeRouteProvider(), parser=parser)

    response = post_plan(client, {"query": "Gdańsk → Den Bosch w czwartek, najtaniej"})

    assert response.status_code == 200
    assert response.json()["parsed_by"] == "ai"
    assert response.json()["priority"] == "cheap"
    assert parser.calls == [("Gdańsk → Den Bosch w czwartek, najtaniej", NOW.date())]


def test_planned_option_can_be_saved_as_trip(client: TestClient) -> None:
    """Integracja: etapy z /api/plan pasują 1:1 do POST /api/trips."""
    override(client, provider=FakeRouteProvider())
    option = post_plan(client, FORM_REQUEST).json()["options"][1]

    response = client.post(
        "/api/trips",
        json={"name": "Do Den Bosch", **FORM_REQUEST, "legs": option["legs"]},
    )

    assert response.status_code == 201
    assert response.json()["total_co2_kg"] == pytest.approx(option["total_co2_kg"])


# --- 422: popraw zapytanie ---


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"query": "Gdańsk → Sopot", "origin": "Gdańsk"},
        {"origin": "Gdańsk", "destination": "Sopot"},
        {"query": "x" * 1001},
    ],
    ids=["empty-body", "query-and-form", "form-without-date", "query-too-long"],
)
def test_invalid_request_shape_returns_422(client: TestClient, body: dict[str, Any]) -> None:
    override(client, provider=FakeRouteProvider())

    assert post_plan(client, body).status_code == 422


def test_past_date_returns_422_with_message(client: TestClient) -> None:
    override(client, provider=FakeRouteProvider())

    response = post_plan(client, {**FORM_REQUEST, "travel_date": "2026-11-12"})

    assert response.status_code == 422
    assert "przeszłości" in response.json()["detail"]


def test_unknown_place_returns_422(client: TestClient) -> None:
    override(client, provider=FakeRouteProvider())

    response = post_plan(client, {**FORM_REQUEST, "destination": "Atlantyda"})

    assert response.status_code == 422
    assert "Atlantyda" in response.json()["detail"]


def test_query_not_understood_returns_422(client: TestClient) -> None:
    parser = FakeIntentParser(error=IntentNotUnderstoodError("Nie rozpoznano miejsca wyjazdu."))
    override(client, provider=FakeRouteProvider(), parser=parser)

    response = post_plan(client, {"query": "chcę gdzieś pojechać"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Nie rozpoznano miejsca wyjazdu."


# --- 503: problem po naszej stronie albo u dostawcy ---


def test_query_without_ai_returns_503(client: TestClient) -> None:
    override(client, provider=FakeRouteProvider(), parser=None)

    response = post_plan(client, {"query": "Gdańsk → Sopot"})

    assert response.status_code == 503
    assert "formularza" in response.json()["detail"]


def test_ai_failure_returns_503(client: TestClient) -> None:
    parser = FakeIntentParser(error=AiUnavailableError("AI nie odpowiedziało na czas."))
    override(client, provider=FakeRouteProvider(), parser=parser)

    assert post_plan(client, {"query": "Gdańsk → Sopot"}).status_code == 503


def test_geocoding_failure_returns_503(client: TestClient) -> None:
    provider = FakeRouteProvider(geocode_error=TransitousUnavailableError("down"))
    override(client, provider=provider)

    assert post_plan(client, FORM_REQUEST).status_code == 503


def test_missing_app_contact_returns_503(client: TestClient) -> None:
    override(client, provider=None)

    response = post_plan(client, FORM_REQUEST)

    assert response.status_code == 503
    assert "APP_CONTACT" in response.json()["detail"]


# --- Składanie aplikacji (lifespan) ---


def test_app_creates_transitous_client_when_contact_is_set(
    client_factory: Callable[..., TestClient],
) -> None:
    client = client_factory(app_contact="https://github.com/example/repo")

    assert isinstance(client.app.state.route_provider, TransitousClient)  # type: ignore[attr-defined]


def test_app_disables_routing_without_contact(client: TestClient) -> None:
    assert client.app.state.route_provider is None  # type: ignore[attr-defined]
    assert client.app.state.intent_parser is None  # type: ignore[attr-defined]
