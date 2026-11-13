"""Planowanie podróży: intencja → geokodowanie → połączenia + szacunek lotu → ranking.

Tu zapadają wszystkie decyzje widoczne dla użytkownika (kolejność opcji, rekomendacja),
więc wszystko jest deterministyczne i testowane. AI niczego tu nie liczy.

Zależności zewnętrzne (Transitous, parser AI) są opisane protokołami (Protocol):
planner wie tylko, jakie METODY mają mieć, a nie jakiej są klasy. Dzięki temu testy
podają proste atrapy, a produkcja — prawdziwe klienty.
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol

from app.models import (
    LegCreate,
    LegSource,
    PlanOption,
    PlanRequest,
    PlanResponse,
    Priority,
    TransportMode,
)
from app.services.emissions import estimate_co2_kg, estimate_flight_duration, haversine_km
from app.services.intent_parser import (
    AiUnavailableError,
    LlmIntentResponse,
    TravelIntent,
    build_travel_intent,
)
from app.services.transitous import (
    TRANSITOUS_SOURCES_URL,
    GeocodedPlace,
    RouteOption,
    TransitousUnavailableError,
)

# Od której godziny (UTC) szukamy połączeń w dniu podróży. 05:00 UTC = 06:00/07:00 w Polsce.
SEARCH_START_HOUR_UTC = 5

# Lot proponujemy dopiero od tego dystansu — krócej nikt rozsądny nie lata,
# a samolot "wygrywałby" ranking czasu tylko dlatego, że nie liczymy dojazdu na lotnisko.
MIN_FLIGHT_DISTANCE_KM = 300.0
FLIGHT_ESTIMATE_DEPARTURE_HOUR_UTC = 8
# Szacunkowy lot "na dziś" nie może startować za 10 minut.
MIN_FLIGHT_LEAD_TIME = timedelta(hours=3)


@dataclass(frozen=True)
class FareAssumption:
    base_eur: float  # stała opłata za etap (np. bilet miejski, opłaty lotniskowe)
    per_km_eur: float


# ORIENTACYJNE CENY — NASZE ZAŁOŻENIA. Transitous nie podaje cen biletów, a priorytet
# "najtaniej" potrzebuje jakiejś miary. To rząd wielkości, nie cennik: UI oznacza koszt
# jako szacunek. Zmieniając te liczby, zmieniasz tylko ranking "cheap".
FARE_ASSUMPTIONS: dict[TransportMode, FareAssumption] = {
    TransportMode.TRAIN: FareAssumption(base_eur=0.0, per_km_eur=0.10),
    TransportMode.BUS: FareAssumption(base_eur=0.0, per_km_eur=0.05),
    TransportMode.FLIGHT: FareAssumption(base_eur=40.0, per_km_eur=0.08),
    TransportMode.TRAM: FareAssumption(base_eur=2.0, per_km_eur=0.0),
    TransportMode.FERRY: FareAssumption(base_eur=5.0, per_km_eur=0.10),
    TransportMode.WALK: FareAssumption(base_eur=0.0, per_km_eur=0.0),
}

ParsedBy = Literal["ai", "form"]


class RouteProvider(Protocol):
    """To, czego planner potrzebuje od źródła połączeń (spełnia to TransitousClient)."""

    def geocode(self, text: str) -> GeocodedPlace: ...

    def plan(
        self, origin: GeocodedPlace, destination: GeocodedPlace, departure: datetime
    ) -> list[RouteOption]: ...


class IntentSource(Protocol):
    """To, czego planner potrzebuje od parsera AI (spełnia to IntentParser)."""

    def parse(self, query: str, today: date) -> TravelIntent: ...


# ---------- Intencja: z AI albo z formularza ----------


def resolve_intent(
    plan_request: PlanRequest, parser: IntentSource | None, today: date
) -> tuple[TravelIntent, ParsedBy]:
    if plan_request.query is not None:
        if parser is None:
            raise AiUnavailableError("AI niedostępne — użyj formularza.")
        return parser.parse(plan_request.query, today), "ai"

    # Formularz przechodzi przez TE SAME reguły co odpowiedź AI (data nie w przeszłości,
    # skąd ≠ dokąd, domyślny priorytet). Jedna funkcja = brak rozjazdu między ścieżkami.
    form_values = LlmIntentResponse(
        origin=plan_request.origin,
        destination=plan_request.destination,
        travel_date=plan_request.travel_date,
        priority=plan_request.priority,
    )
    return build_travel_intent(form_values, today), "form"


# ---------- Czas ----------


def search_start(travel_date: date, now: datetime) -> datetime:
    """Początek wyszukiwania: rano w dniu podróży, ale nie w przeszłości."""
    morning = datetime.combine(travel_date, time(SEARCH_START_HOUR_UTC), tzinfo=UTC)
    return max(morning, now)


def round_up_to_full_hour(moment: datetime) -> datetime:
    full_hour = moment.replace(minute=0, second=0, microsecond=0)
    return full_hour if full_hour == moment else full_hour + timedelta(hours=1)


def round_to_five_minutes(duration: timedelta) -> timedelta:
    # Szacunek z dokładnością do minuty udawałby precyzję, której nie mamy.
    return timedelta(minutes=5 * round(duration.total_seconds() / 60 / 5))


# ---------- Szacunek lotu ----------


def estimate_flight(
    origin_label: str,
    destination_label: str,
    origin: GeocodedPlace,
    destination: GeocodedPlace,
    travel_date: date,
    now: datetime,
) -> list[LegCreate] | None:
    """Lot "miasto → miasto" po ortodromie. Nie sprawdzamy, czy jest tam lotnisko —
    to szacunek do porównania (source=ESTIMATE), a nie oferta linii lotniczej."""
    distance_km = haversine_km(origin.coordinates, destination.coordinates)
    if distance_km < MIN_FLIGHT_DISTANCE_KM:
        return None

    planned_departure = datetime.combine(
        travel_date, time(FLIGHT_ESTIMATE_DEPARTURE_HOUR_UTC), tzinfo=UTC
    )
    earliest_departure = round_up_to_full_hour(now + MIN_FLIGHT_LEAD_TIME)
    departure = max(planned_departure, earliest_departure)
    duration = round_to_five_minutes(estimate_flight_duration(distance_km))

    return [
        LegCreate(
            mode=TransportMode.FLIGHT,
            from_place=origin_label,
            to_place=destination_label,
            departure=departure,
            arrival=departure + duration,
            distance_km=round(distance_km, 3),
            co2_kg=round(estimate_co2_kg(TransportMode.FLIGHT, distance_km), 3),
            source=LegSource.ESTIMATE,
        )
    ]


# ---------- Podsumowanie i ranking ----------


def estimate_cost_eur(legs: list[LegCreate]) -> float:
    total = 0.0
    for leg in legs:
        fare = FARE_ASSUMPTIONS[leg.mode]
        total += fare.base_eur + fare.per_km_eur * leg.distance_km
    return float(round(total))  # pełne euro — to i tak rząd wielkości


def summarize_option(legs: list[LegCreate], transfers: int) -> PlanOption:
    if not legs:
        raise ValueError("Opcja musi mieć co najmniej jeden etap")
    departure = legs[0].departure
    arrival = legs[-1].arrival
    return PlanOption(
        legs=legs,
        transfers=transfers,
        departure=departure,
        arrival=arrival,
        duration_minutes=math.ceil((arrival - departure).total_seconds() / 60),
        total_distance_km=round(sum(leg.distance_km for leg in legs), 3),
        total_co2_kg=round(sum(leg.co2_kg for leg in legs), 3),
        estimated_cost_eur=estimate_cost_eur(legs),
        is_estimate=any(leg.source is LegSource.ESTIMATE for leg in legs),
    )


def ranking_key(option: PlanOption, priority: Priority) -> tuple[float, float, float]:
    """Najpierw kryterium z priorytetu, potem dwa pozostałe jako rozstrzygnięcie remisu."""
    duration = float(option.duration_minutes)
    co2 = option.total_co2_kg
    cost = option.estimated_cost_eur
    match priority:
        case Priority.FAST:
            return (duration, co2, cost)
        case Priority.GREEN:
            return (co2, duration, cost)
        case Priority.CHEAP:
            return (cost, duration, co2)


def rank_options(options: list[PlanOption], priority: Priority) -> list[PlanOption]:
    """Zwraca NOWĄ, posortowaną listę; pierwsza opcja ma recommended=True."""
    ranked = sorted(options, key=lambda option: ranking_key(option, priority))
    # model_copy zamiast ranked[0].recommended = True — nie zmieniamy obiektów wejściowych.
    return [
        option.model_copy(update={"recommended": index == 0}) for index, option in enumerate(ranked)
    ]


def format_duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return f"{rest} min"
    return f"{hours} h {rest:02d} min"


def format_transfers(count: int) -> str:
    """Polska odmiana: 1 przesiadka, 2–4 przesiadki, 5+ przesiadek (ale 12–14 przesiadek)."""
    if count == 0:
        return "bez przesiadek"
    if count == 1:
        return "1 przesiadka"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} przesiadki"
    return f"{count} przesiadek"


RECOMMENDATION_PREFIX: dict[Priority, str] = {
    Priority.FAST: "Najszybsza opcja",
    Priority.GREEN: "Najniższa emisja CO₂",
    Priority.CHEAP: "Najtańsza opcja (szacunkowo)",
}


def describe_recommendation(option: PlanOption, priority: Priority) -> str:
    sentence = (
        f"{RECOMMENDATION_PREFIX[priority]}: {format_duration(option.duration_minutes)}, "
        f"{format_transfers(option.transfers)}, {option.total_co2_kg:.1f} kg CO₂e, "
        f"ok. {option.estimated_cost_eur:.0f} €."
    )
    if option.is_estimate:
        sentence += " Czas i emisja lotu to szacunek."
    return sentence


# ---------- Całość ----------


def build_plan(
    intent: TravelIntent, parsed_by: ParsedBy, provider: RouteProvider, now: datetime
) -> PlanResponse:
    # Geokodowanie musi się udać — bez współrzędnych nie policzymy niczego.
    # PlaceNotFoundError i TransitousUnavailableError lecą wyżej, do routera.
    origin = provider.geocode(intent.origin)
    destination = provider.geocode(intent.destination)

    options: list[PlanOption] = []
    warnings: list[str] = []

    try:
        routes = provider.plan(origin, destination, search_start(intent.travel_date, now))
        options.extend(summarize_option(route.legs, route.transfers) for route in routes)
    except TransitousUnavailableError:
        # Łagodna degradacja: brak rozkładu nie przekreśla szacunku lotu.
        warnings.append("Rozkład jazdy jest chwilowo niedostępny — spróbuj ponownie za chwilę.")

    flight_legs = estimate_flight(
        intent.origin, intent.destination, origin, destination, intent.travel_date, now
    )
    if flight_legs is not None:
        options.append(summarize_option(flight_legs, transfers=0))

    if not options:
        warnings.append("Nie znaleziono połączeń dla tej trasy i daty.")

    ranked = rank_options(options, intent.priority)
    return PlanResponse(
        origin=intent.origin,
        destination=intent.destination,
        origin_name=origin.name,
        destination_name=destination.name,
        travel_date=intent.travel_date,
        priority=intent.priority,
        parsed_by=parsed_by,
        options=ranked,
        recommendation=describe_recommendation(ranked[0], intent.priority) if ranked else None,
        warnings=warnings,
        data_sources_url=TRANSITOUS_SOURCES_URL,
    )
