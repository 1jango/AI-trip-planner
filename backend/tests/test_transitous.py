"""Testy klienta Transitous bez internetu: httpx.MockTransport udaje serwer.

Dane w odpowiedziach są ręcznie przygotowane według specyfikacji MOTIS 2 (openapi.yaml),
w uproszczeniu — zawierają tylko pola, których używa nasz klient (+ jedno nadmiarowe).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.database import create_db_and_tables, create_db_engine
from app.models import LegSource, TransportMode
from app.services.cache import ResponseCache
from app.services.emissions import Coordinates, haversine_km
from app.services.transitous import (
    DEFAULT_TIMEOUT,
    GeocodedPlace,
    PlaceNotFoundError,
    TransitousClient,
    TransitousUnavailableError,
    build_user_agent,
    create_http_client,
)

USER_AGENT = "AI-Trip-Planner/0.1.0 (test@example.com)"
DEPARTURE = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)

GDANSK = GeocodedPlace("Gdańsk Główny", Coordinates(54.3556, 18.6440), stop_id="pl_gdansk_glowny")
BERLIN = GeocodedPlace("Berlin Hbf", Coordinates(52.5251, 13.3694))

GEOCODE_RESPONSE: list[dict[str, Any]] = [
    {
        "type": "STOP",
        "id": "pl_gdansk_glowny",
        "name": "Gdańsk Główny",
        "lat": 54.3556,
        "lon": 18.6440,
        "tokens": [],
        "areas": [],
        "score": 1.0,
    },
    {
        "type": "PLACE",
        "id": "osm_gdansk",
        "name": "Gdańsk",
        "lat": 54.35,
        "lon": 18.65,
        "tokens": [],
        "areas": [],
        "score": 0.8,
    },
]


def make_place(name: str, lat: float, lon: float) -> dict[str, Any]:
    return {"name": name, "lat": lat, "lon": lon}


def make_leg(
    mode: str,
    start: dict[str, Any],
    end: dict[str, Any],
    start_time: str,
    end_time: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "from": start,
        "to": end,
        "startTime": start_time,
        "endTime": end_time,
        "legGeometry": {"points": "", "precision": 6, "length": 0},  # pole, którego nie używamy
        **extra,
    }


STATION = make_place("Gdańsk Główny", 54.3556, 18.6440)
BYDGOSZCZ = make_place("Bydgoszcz Główna", 53.1350, 17.9898)
POZNAN = make_place("Poznań Główny", 52.4011, 16.9116)
BERLIN_HBF = make_place("Berlin Hbf", 52.5251, 13.3694)
BERLIN_ZOO = make_place("Berlin Zoologischer Garten", 52.5070, 13.3324)

PLAN_RESPONSE: dict[str, Any] = {
    "requestParameters": {},
    "debugOutput": {},
    "from": STATION,
    "to": BERLIN_HBF,
    "direct": [],
    "previousPageCursor": "",
    "nextPageCursor": "",
    "itineraries": [
        {
            "duration": 23400,
            "startTime": "2026-11-19T08:00:00Z",
            "endTime": "2026-11-19T14:30:00Z",
            "transfers": 0,
            "legs": [
                make_leg(
                    "WALK",
                    make_place("START", 54.3580, 18.6450),
                    STATION,
                    "2026-11-19T08:00:00Z",
                    "2026-11-19T08:05:00Z",
                    distance=350.0,
                ),
                make_leg(
                    "LONG_DISTANCE",
                    STATION,
                    BERLIN_HBF,
                    "2026-11-19T08:10:00Z",
                    "2026-11-19T14:00:00Z",
                    intermediateStops=[BYDGOSZCZ, POZNAN],
                ),
                make_leg(
                    "BUS",
                    BERLIN_HBF,
                    BERLIN_ZOO,
                    "2026-11-19T14:10:00Z",
                    "2026-11-19T14:30:00Z",
                ),
            ],
        },
        {
            # Trasa z samochodem — nieobsługiwany tryb, klient powinien ją pominąć.
            "duration": 20000,
            "startTime": "2026-11-19T09:00:00Z",
            "endTime": "2026-11-19T14:33:20Z",
            "transfers": 0,
            "legs": [
                make_leg("CAR", STATION, BERLIN_HBF, "2026-11-19T09:00:00Z", "2026-11-19T14:33:20Z")
            ],
        },
    ],
}


class FakeTransitousServer:
    """Udaje serwer: zwraca przygotowaną odpowiedź i zapamiętuje otrzymane zapytania."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def json_response(
    payload: Any, status_code: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(status_code, json=payload)


def make_client(
    server: FakeTransitousServer, cache: ResponseCache | None = None
) -> TransitousClient:
    http_client = httpx.Client(
        base_url="https://api.transitous.org",
        headers={"User-Agent": USER_AGENT},
        transport=httpx.MockTransport(server),  # zamiast sieci — nasza funkcja
    )
    return TransitousClient(http_client, cache=cache)


# ---------- User-Agent i konfiguracja ----------


def test_build_user_agent_contains_name_version_and_contact() -> None:
    user_agent = build_user_agent("AI Trip Planner", "0.1.0", "jan@example.com")

    assert user_agent == "AI-Trip-Planner/0.1.0 (jan@example.com)"


@pytest.mark.parametrize("empty_contact", ["", "   "])
def test_build_user_agent_requires_contact(empty_contact: str) -> None:
    with pytest.raises(ValueError, match="APP_CONTACT"):
        build_user_agent("AI Trip Planner", "0.1.0", empty_contact)


def test_http_client_has_user_agent_and_timeout() -> None:
    with create_http_client("https://api.transitous.org", USER_AGENT) as http_client:
        assert http_client.headers["User-Agent"] == USER_AGENT
        assert http_client.timeout == DEFAULT_TIMEOUT


def test_every_request_sends_user_agent() -> None:
    server = FakeTransitousServer(json_response(GEOCODE_RESPONSE))

    make_client(server).geocode("Gdańsk")

    assert server.requests[0].headers["User-Agent"] == USER_AGENT


# ---------- Geokodowanie ----------


def test_geocode_returns_best_match_with_stop_id() -> None:
    server = FakeTransitousServer(json_response(GEOCODE_RESPONSE))

    place = make_client(server).geocode("  Gdańsk  ")

    assert place.name == "Gdańsk Główny"
    assert place.stop_id == "pl_gdansk_glowny"
    assert place.coordinates == Coordinates(54.3556, 18.6440)
    assert server.requests[0].url.path == "/api/v1/geocode"
    assert server.requests[0].url.params["text"] == "Gdańsk"  # bez spacji z brzegów


def test_geocode_of_non_stop_has_no_stop_id() -> None:
    server = FakeTransitousServer(json_response(GEOCODE_RESPONSE[1:]))

    place = make_client(server).geocode("Gdańsk")

    assert place.stop_id is None


def test_geocode_with_no_results_raises_place_not_found() -> None:
    server = FakeTransitousServer(json_response([]))

    with pytest.raises(PlaceNotFoundError):
        make_client(server).geocode("Xyzzyville")


def test_geocode_rejects_empty_text_without_calling_api() -> None:
    server = FakeTransitousServer(json_response(GEOCODE_RESPONSE))

    with pytest.raises(ValueError):
        make_client(server).geocode("   ")

    assert server.requests == []


def test_place_uses_stop_id_or_coordinates_for_motis() -> None:
    assert GDANSK.as_motis_place() == "pl_gdansk_glowny"
    assert BERLIN.as_motis_place() == "52.5251,13.3694"


# ---------- Wyszukiwanie połączeń ----------


def test_plan_sends_expected_query_parameters() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))
    departure_utc = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)

    make_client(server).plan(GDANSK, BERLIN, departure_utc)

    params = server.requests[0].url.params
    assert server.requests[0].url.path == "/api/v6/plan"
    assert params["fromPlace"] == "pl_gdansk_glowny"
    assert params["toPlace"] == "52.5251,13.3694"
    assert params["time"] == "2026-11-19T09:00:00Z"
    assert params["detailedLegs"] == "false"


def test_plan_converts_departure_to_utc() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))
    warsaw = datetime.fromisoformat("2026-11-19T09:00:00+01:00")

    make_client(server).plan(GDANSK, BERLIN, warsaw)

    assert server.requests[0].url.params["time"] == "2026-11-19T08:00:00Z"


def test_plan_rejects_naive_departure() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))

    with pytest.raises(ValueError):
        make_client(server).plan(GDANSK, BERLIN, datetime(2026, 11, 19, 8, 0))


def test_plan_maps_legs_and_skips_unsupported_itineraries() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))

    options = make_client(server).plan(GDANSK, BERLIN, DEPARTURE)

    assert len(options) == 1  # trasa z CAR pominięta
    option = options[0]
    assert option.transfers == 0
    assert [leg.mode for leg in option.legs] == [
        TransportMode.WALK,
        TransportMode.TRAIN,
        TransportMode.BUS,
    ]
    assert all(leg.source is LegSource.TRANSITOUS for leg in option.legs)
    assert option.departure == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    assert option.arrival == datetime(2026, 11, 19, 14, 30, tzinfo=UTC)


def test_walk_leg_uses_distance_from_api_in_meters() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))

    walk_leg = make_client(server).plan(GDANSK, BERLIN, DEPARTURE)[0].legs[0]

    assert walk_leg.distance_km == pytest.approx(0.35)
    assert walk_leg.co2_kg == 0


def test_train_distance_follows_intermediate_stops() -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))

    train_leg = make_client(server).plan(GDANSK, BERLIN, DEPARTURE)[0].legs[1]

    # Oczekiwany dystans liczymy niezależnie: suma odcinków między kolejnymi przystankami.
    stops = [STATION, BYDGOSZCZ, POZNAN, BERLIN_HBF]
    expected_km = sum(
        haversine_km(Coordinates(a["lat"], a["lon"]), Coordinates(b["lat"], b["lon"]))
        for a, b in zip(stops, stops[1:], strict=False)
    )
    direct_km = haversine_km(Coordinates(54.3556, 18.6440), Coordinates(52.5251, 13.3694))
    assert train_leg.distance_km == pytest.approx(expected_km, abs=0.001)
    assert train_leg.distance_km > direct_km  # objazd przez Poznań jest dłuższy niż "na wprost"
    assert train_leg.co2_kg == pytest.approx(expected_km * 0.03546, abs=0.001)


def test_plan_with_no_itineraries_returns_empty_list() -> None:
    server = FakeTransitousServer(json_response({**PLAN_RESPONSE, "itineraries": []}))

    assert make_client(server).plan(GDANSK, BERLIN, DEPARTURE) == []


# ---------- Błędy ----------


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def raise_connection_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        raise_timeout,
        raise_connection_error,
        json_response({"error": "internal"}, status_code=500),
        json_response({"error": "rate limited"}, status_code=429),
        lambda _request: httpx.Response(200, text="<html>not json</html>"),
        json_response({"unexpected": "shape"}),  # brak pola "itineraries"
    ],
    ids=["timeout", "connection-error", "http-500", "http-429", "not-json", "wrong-shape"],
)
def test_api_problems_raise_transitous_unavailable(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    server = FakeTransitousServer(handler)

    with pytest.raises(TransitousUnavailableError):
        make_client(server).plan(GDANSK, BERLIN, DEPARTURE)


# ---------- Cache ----------


@pytest.fixture
def cache() -> ResponseCache:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    return ResponseCache(engine)


def test_repeated_query_is_served_from_cache(cache: ResponseCache) -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))
    client = make_client(server, cache=cache)

    first = client.plan(GDANSK, BERLIN, DEPARTURE)
    second = client.plan(GDANSK, BERLIN, DEPARTURE)

    assert len(server.requests) == 1  # drugie zapytanie nie poszło do "sieci"
    assert first == second


def test_different_query_is_not_served_from_cache(cache: ResponseCache) -> None:
    server = FakeTransitousServer(json_response(PLAN_RESPONSE))
    client = make_client(server, cache=cache)

    client.plan(GDANSK, BERLIN, DEPARTURE)
    client.plan(GDANSK, BERLIN, DEPARTURE + timedelta(hours=1))

    assert len(server.requests) == 2


def test_errors_are_not_cached(cache: ResponseCache) -> None:
    responses = iter(
        [httpx.Response(503, json={"error": "busy"}), httpx.Response(200, json=PLAN_RESPONSE)]
    )
    server = FakeTransitousServer(lambda _request: next(responses))
    client = make_client(server, cache=cache)

    with pytest.raises(TransitousUnavailableError):
        client.plan(GDANSK, BERLIN, DEPARTURE)
    options = client.plan(GDANSK, BERLIN, DEPARTURE)

    assert len(options) == 1
    assert len(server.requests) == 2
