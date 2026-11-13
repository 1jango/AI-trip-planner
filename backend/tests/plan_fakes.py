"""Atrapy i dane wspólne dla testów planera i endpointu /api/plan.

Atrapy spełniają protokoły RouteProvider i IntentSource — nie dziedziczą po prawdziwych
klasach, mają tylko te same metody. To wystarcza (tzw. typowanie strukturalne).
"""

from datetime import UTC, date, datetime

from app.models import LegCreate, LegSource, Priority, TransportMode
from app.services.emissions import Coordinates
from app.services.intent_parser import TravelIntent
from app.services.transitous import GeocodedPlace, PlaceNotFoundError, RouteOption

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)  # piątek, południe UTC
TODAY = NOW.date()
TRAVEL_DATE = date(2026, 11, 19)

GDANSK = GeocodedPlace("Gdańsk Główny", Coordinates(54.3556, 18.6440), stop_id="pl_gdansk")
DEN_BOSCH = GeocodedPlace("'s-Hertogenbosch", Coordinates(51.6906, 5.2934), stop_id="nl_db")
SOPOT = GeocodedPlace("Sopot", Coordinates(54.4416, 18.5601), stop_id="pl_sopot")

PLACES = {"Gdańsk": GDANSK, "'s-Hertogenbosch": DEN_BOSCH, "Sopot": SOPOT}


def make_leg(
    mode: TransportMode,
    departure: str,
    arrival: str,
    distance_km: float,
    co2_kg: float,
    from_place: str = "A",
    to_place: str = "B",
) -> LegCreate:
    return LegCreate(
        mode=mode,
        from_place=from_place,
        to_place=to_place,
        departure=datetime.fromisoformat(departure),
        arrival=datetime.fromisoformat(arrival),
        distance_km=distance_km,
        co2_kg=co2_kg,
        source=LegSource.TRANSITOUS,
    )


# Pociąg Gdańsk → 's-Hertogenbosch z jedną przesiadką: 14 h 30 min, 1100 km.
TRAIN_ROUTE = RouteOption(
    legs=[
        make_leg(
            TransportMode.TRAIN,
            "2026-11-19T05:30:00+00:00",
            "2026-11-19T12:00:00+00:00",
            600.0,
            21.276,
            from_place="Gdańsk Główny",
            to_place="Berlin Hbf",
        ),
        make_leg(
            TransportMode.TRAIN,
            "2026-11-19T12:30:00+00:00",
            "2026-11-19T20:00:00+00:00",
            500.0,
            17.73,
            from_place="Berlin Hbf",
            to_place="'s-Hertogenbosch",
        ),
    ],
    transfers=1,
)


class FakeRouteProvider:
    def __init__(
        self,
        routes: list[RouteOption] | None = None,
        plan_error: Exception | None = None,
        geocode_error: Exception | None = None,
    ) -> None:
        self.routes = routes if routes is not None else [TRAIN_ROUTE]
        self.plan_error = plan_error
        self.geocode_error = geocode_error
        self.plan_calls: list[tuple[GeocodedPlace, GeocodedPlace, datetime]] = []

    def geocode(self, text: str) -> GeocodedPlace:
        if self.geocode_error is not None:
            raise self.geocode_error
        if text not in PLACES:
            raise PlaceNotFoundError(f"Nie znaleziono miejsca: {text}")
        return PLACES[text]

    def plan(
        self, origin: GeocodedPlace, destination: GeocodedPlace, departure: datetime
    ) -> list[RouteOption]:
        self.plan_calls.append((origin, destination, departure))
        if self.plan_error is not None:
            raise self.plan_error
        return self.routes


class FakeIntentParser:
    def __init__(self, intent: TravelIntent | None = None, error: Exception | None = None) -> None:
        self.intent = intent or TravelIntent(
            origin="Gdańsk",
            destination="'s-Hertogenbosch",
            travel_date=TRAVEL_DATE,
            priority=Priority.CHEAP,
        )
        self.error = error
        self.calls: list[tuple[str, date]] = []

    def parse(self, query: str, today: date) -> TravelIntent:
        self.calls.append((query, today))
        if self.error is not None:
            raise self.error
        return self.intent
