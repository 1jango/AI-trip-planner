"""Testy czystej logiki planera: czas, szacunek lotu, koszt, ranking, rekomendacja."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import LegSource, PlanOption, PlanRequest, Priority, TransportMode
from app.services.emissions import (
    EMISSION_FACTORS_KG_PER_PASSENGER_KM,
    estimate_flight_duration,
    haversine_km,
)
from app.services.intent_parser import (
    DEFAULT_PRIORITY,
    AiUnavailableError,
    IntentNotUnderstoodError,
    TravelIntent,
)
from app.services.planner import (
    FARE_ASSUMPTIONS,
    build_plan,
    describe_recommendation,
    estimate_cost_eur,
    estimate_flight,
    format_duration,
    format_transfers,
    rank_options,
    resolve_intent,
    round_to_five_minutes,
    round_up_to_full_hour,
    search_start,
    summarize_option,
)
from app.services.transitous import (
    TRANSITOUS_SOURCES_URL,
    PlaceNotFoundError,
    TransitousUnavailableError,
)
from tests.plan_fakes import (
    DEN_BOSCH,
    GDANSK,
    NOW,
    SOPOT,
    TODAY,
    TRAIN_ROUTE,
    TRAVEL_DATE,
    FakeIntentParser,
    FakeRouteProvider,
    make_leg,
)

# --- Czas ---


def test_search_starts_in_the_morning_of_a_future_travel_date() -> None:
    assert search_start(TRAVEL_DATE, NOW) == datetime(2026, 11, 19, 5, 0, tzinfo=UTC)


def test_search_for_today_starts_now_not_in_the_past() -> None:
    assert search_start(TODAY, NOW) == NOW


@pytest.mark.parametrize(
    ("moment", "expected_hour"),
    [
        (datetime(2026, 11, 13, 12, 0, tzinfo=UTC), 12),
        (datetime(2026, 11, 13, 12, 1, tzinfo=UTC), 13),
    ],
    ids=["full-hour-stays", "rounds-up"],
)
def test_round_up_to_full_hour(moment: datetime, expected_hour: int) -> None:
    assert round_up_to_full_hour(moment) == moment.replace(hour=expected_hour, minute=0)


@pytest.mark.parametrize(
    ("minutes", "expected"), [(92, 90), (93, 95), (2, 0)], ids=["down", "up", "to-zero"]
)
def test_round_to_five_minutes(minutes: int, expected: int) -> None:
    assert round_to_five_minutes(timedelta(minutes=minutes)) == timedelta(minutes=expected)


# --- Szacunek lotu ---


def test_no_flight_for_short_distance() -> None:
    assert estimate_flight("Gdańsk", "Sopot", GDANSK, SOPOT, TRAVEL_DATE, NOW) is None


def test_flight_estimate_for_long_distance() -> None:
    legs = estimate_flight("Gdańsk", "'s-Hertogenbosch", GDANSK, DEN_BOSCH, TRAVEL_DATE, NOW)

    assert legs is not None and len(legs) == 1
    flight = legs[0]
    distance = haversine_km(GDANSK.coordinates, DEN_BOSCH.coordinates)
    assert flight.mode is TransportMode.FLIGHT
    assert flight.source is LegSource.ESTIMATE
    # Nazwy z zapytania użytkownika, a nie nazwy stacji z geokodowania.
    assert (flight.from_place, flight.to_place) == ("Gdańsk", "'s-Hertogenbosch")
    assert flight.departure == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    assert flight.arrival - flight.departure == round_to_five_minutes(
        estimate_flight_duration(distance)
    )
    assert flight.distance_km == pytest.approx(distance, abs=0.001)
    assert flight.co2_kg == pytest.approx(
        distance * EMISSION_FACTORS_KG_PER_PASSENGER_KM[TransportMode.FLIGHT], abs=0.001
    )


def test_flight_for_today_departs_after_lead_time() -> None:
    legs = estimate_flight("Gdańsk", "'s-Hertogenbosch", GDANSK, DEN_BOSCH, TODAY, NOW)

    assert legs is not None
    # 12:00 + 3 h = 15:00 (już pełna godzina), a nie 08:00, które minęło.
    assert legs[0].departure == datetime(2026, 11, 13, 15, 0, tzinfo=UTC)


# --- Koszt i podsumowanie ---


def test_every_transport_mode_has_fare_assumption() -> None:
    assert set(FARE_ASSUMPTIONS) == set(TransportMode)


@pytest.mark.parametrize(
    ("mode", "distance_km", "expected_eur"),
    [
        (TransportMode.TRAIN, 500.0, 50.0),  # 500 × 0,10
        (TransportMode.BUS, 500.0, 25.0),  # 500 × 0,05
        (TransportMode.FLIGHT, 1000.0, 120.0),  # 40 + 1000 × 0,08
        (TransportMode.TRAM, 7.0, 2.0),  # bilet miejski, niezależnie od dystansu
        (TransportMode.WALK, 1.0, 0.0),
    ],
)
def test_estimate_cost_eur(mode: TransportMode, distance_km: float, expected_eur: float) -> None:
    leg = make_leg(mode, "2026-11-19T08:00:00+00:00", "2026-11-19T09:00:00+00:00", distance_km, 1)

    assert estimate_cost_eur([leg]) == expected_eur


def test_summarize_option_totals() -> None:
    option = summarize_option(TRAIN_ROUTE.legs, TRAIN_ROUTE.transfers)

    assert option.departure == datetime(2026, 11, 19, 5, 30, tzinfo=UTC)
    assert option.arrival == datetime(2026, 11, 19, 20, 0, tzinfo=UTC)
    assert option.duration_minutes == 14 * 60 + 30
    assert option.total_distance_km == 1100.0
    assert option.total_co2_kg == pytest.approx(21.276 + 17.73)
    assert option.estimated_cost_eur == 110.0
    assert option.transfers == 1
    assert option.is_estimate is False
    assert option.recommended is False


def test_summarize_option_requires_legs() -> None:
    with pytest.raises(ValueError):
        summarize_option([], transfers=0)


# --- Ranking ---


def make_option(label: str, duration_minutes: int, co2_kg: float, cost_eur: float) -> PlanOption:
    departure = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    arrival = departure + timedelta(minutes=duration_minutes)
    leg = make_leg(
        TransportMode.TRAIN, departure.isoformat(), arrival.isoformat(), 100, co2_kg, label
    )
    return PlanOption(
        legs=[leg],
        transfers=0,
        departure=departure,
        arrival=arrival,
        duration_minutes=duration_minutes,
        total_distance_km=100,
        total_co2_kg=co2_kg,
        estimated_cost_eur=cost_eur,
        is_estimate=False,
    )


# Każda opcja wygrywa w innej kategorii — test sprawdza, że priorytet naprawdę decyduje.
FLIGHT = make_option("flight", duration_minutes=180, co2_kg=140.0, cost_eur=120.0)
TRAIN = make_option("train", duration_minutes=600, co2_kg=20.0, cost_eur=100.0)
BUS = make_option("bus", duration_minutes=900, co2_kg=28.0, cost_eur=50.0)


def labels(options: list[PlanOption]) -> list[str]:
    return [option.legs[0].from_place for option in options]


@pytest.mark.parametrize(
    ("priority", "expected_order"),
    [
        (Priority.FAST, ["flight", "train", "bus"]),
        (Priority.GREEN, ["train", "bus", "flight"]),
        (Priority.CHEAP, ["bus", "train", "flight"]),
    ],
)
def test_rank_options_by_priority(priority: Priority, expected_order: list[str]) -> None:
    ranked = rank_options([FLIGHT, TRAIN, BUS], priority)

    assert labels(ranked) == expected_order
    assert [option.recommended for option in ranked] == [True, False, False]


def test_ties_are_broken_by_secondary_criteria() -> None:
    slow = make_option("slow", duration_minutes=700, co2_kg=20.0, cost_eur=10.0)
    fast = make_option("fast", duration_minutes=600, co2_kg=20.0, cost_eur=90.0)

    # Ta sama emisja → przy "green" wygrywa krótszy czas.
    assert labels(rank_options([slow, fast], Priority.GREEN)) == ["fast", "slow"]


def test_rank_options_does_not_mutate_input() -> None:
    options = [BUS, FLIGHT]

    rank_options(options, Priority.FAST)

    assert labels(options) == ["bus", "flight"]
    assert all(option.recommended is False for option in options)


def test_rank_empty_list() -> None:
    assert rank_options([], Priority.FAST) == []


# --- Teksty ---


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "bez przesiadek"),
        (1, "1 przesiadka"),
        (2, "2 przesiadki"),
        (4, "4 przesiadki"),
        (5, "5 przesiadek"),
        (11, "11 przesiadek"),
        (12, "12 przesiadek"),
        (14, "14 przesiadek"),
        (22, "22 przesiadki"),
        (25, "25 przesiadek"),
    ],
)
def test_format_transfers_polish_plural(count: int, expected: str) -> None:
    assert format_transfers(count) == expected


@pytest.mark.parametrize(
    ("minutes", "expected"), [(45, "45 min"), (60, "1 h 00 min"), (125, "2 h 05 min")]
)
def test_format_duration(minutes: int, expected: str) -> None:
    assert format_duration(minutes) == expected


def test_recommendation_mentions_estimate_for_flights() -> None:
    flight = FLIGHT.model_copy(update={"is_estimate": True})

    sentence = describe_recommendation(flight, Priority.FAST)

    assert sentence.startswith("Najszybsza opcja: 3 h 00 min, bez przesiadek, 140.0 kg CO₂e")
    assert sentence.endswith("Czas i emisja lotu to szacunek.")


# --- Intencja: AI albo formularz ---


def test_form_request_uses_shared_business_rules_and_default_priority() -> None:
    request = PlanRequest(origin=" Gdańsk ", destination="Sopot", travel_date=TRAVEL_DATE)

    intent, parsed_by = resolve_intent(request, parser=None, today=TODAY)

    assert parsed_by == "form"
    assert intent.origin == "Gdańsk"
    assert intent.priority == DEFAULT_PRIORITY


def test_form_request_with_past_date_is_rejected() -> None:
    yesterday = TODAY - timedelta(days=1)
    request = PlanRequest(origin="Gdańsk", destination="Sopot", travel_date=yesterday)

    with pytest.raises(IntentNotUnderstoodError, match="przeszłości"):
        resolve_intent(request, parser=None, today=TODAY)


def test_query_request_goes_to_ai_parser_with_today() -> None:
    parser = FakeIntentParser()

    intent, parsed_by = resolve_intent(PlanRequest(query="Gdańsk → Den Bosch"), parser, TODAY)

    assert parsed_by == "ai"
    assert intent == parser.intent
    assert parser.calls == [("Gdańsk → Den Bosch", TODAY)]


def test_query_without_ai_raises_ai_unavailable() -> None:
    with pytest.raises(AiUnavailableError, match="formularza"):
        resolve_intent(PlanRequest(query="Gdańsk → Sopot"), parser=None, today=TODAY)


# --- Cały plan ---

LONG_TRIP = TravelIntent(
    origin="Gdańsk",
    destination="'s-Hertogenbosch",
    travel_date=TRAVEL_DATE,
    priority=Priority.GREEN,
)
SHORT_TRIP = TravelIntent(
    origin="Gdańsk", destination="Sopot", travel_date=TRAVEL_DATE, priority=Priority.FAST
)


def test_build_plan_combines_transit_and_flight_estimate() -> None:
    provider = FakeRouteProvider()

    plan = build_plan(LONG_TRIP, "form", provider, NOW)

    assert [option.legs[0].mode for option in plan.options] == [
        TransportMode.TRAIN,  # "green": pociąg ma mniejszą emisję niż lot
        TransportMode.FLIGHT,
    ]
    assert plan.options[0].recommended is True
    assert plan.options[1].is_estimate is True
    assert plan.recommendation is not None
    assert plan.recommendation.startswith("Najniższa emisja CO₂")
    assert (plan.origin_name, plan.destination_name) == ("Gdańsk Główny", "'s-Hertogenbosch")
    assert plan.data_sources_url == TRANSITOUS_SOURCES_URL
    assert plan.warnings == []
    assert provider.plan_calls == [(GDANSK, DEN_BOSCH, datetime(2026, 11, 19, 5, tzinfo=UTC))]


def test_build_plan_falls_back_to_flight_when_timetable_is_down() -> None:
    provider = FakeRouteProvider(plan_error=TransitousUnavailableError("down"))

    plan = build_plan(LONG_TRIP, "form", provider, NOW)

    assert [option.legs[0].mode for option in plan.options] == [TransportMode.FLIGHT]
    assert len(plan.warnings) == 1
    assert "niedostępny" in plan.warnings[0]


def test_build_plan_without_any_option() -> None:
    provider = FakeRouteProvider(plan_error=TransitousUnavailableError("down"))

    plan = build_plan(SHORT_TRIP, "form", provider, NOW)

    assert plan.options == []
    assert plan.recommendation is None
    assert len(plan.warnings) == 2


def test_build_plan_propagates_unknown_place() -> None:
    intent = LONG_TRIP.model_copy(update={"destination": "Atlantyda"})

    with pytest.raises(PlaceNotFoundError):
        build_plan(intent, "form", FakeRouteProvider(), NOW)
