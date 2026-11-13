"""Klient Transitous (MOTIS 2): geokodowanie i wyszukiwanie połączeń.

Zasady użycia API (https://transitous.org/api/):
- każde zapytanie ma nagłówek User-Agent z nazwą aplikacji, wersją i kontaktem,
- mało zapytań (> 720 /plan na dobę to już "duży ruch") — dlatego cache,
- w UI widoczny link do https://transitous.org/sources/ (atrybucja źródeł danych),
- tylko projekty open source i niekomercyjne.

Specyfikacja: openapi.yaml z repozytorium motis-project/motis (tag v2.10.2).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.models import LegCreate, LegSource, TransportMode
from app.services.cache import ResponseCache, make_cache_key
from app.services.emissions import Coordinates, estimate_co2_kg, haversine_km

TRANSITOUS_SOURCES_URL = "https://transitous.org/sources/"

# connect=5 s: tyle czekamy na samo nawiązanie połączenia; 10 s: na całą resztę (odczyt itd.).
# Bez timeoutu zawieszony serwer zawiesiłby nasz endpoint na zawsze.
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Nazwy miejsc i przystanków zmieniają się rzadko; rozkład — częściej (opóźnienia, odwołania).
GEOCODE_CACHE_TTL = timedelta(days=30)
PLAN_CACHE_TTL = timedelta(hours=1)

GEOCODE_PATH = "/api/v1/geocode"
PLAN_PATH = "/api/v6/plan"

# MOTIS zna ~30 trybów; sprowadzamy je do naszych, dla których mamy współczynniki CO₂.
MOTIS_MODE_TO_TRANSPORT_MODE: dict[str, TransportMode] = {
    "RAIL": TransportMode.TRAIN,
    "HIGHSPEED_RAIL": TransportMode.TRAIN,
    "LONG_DISTANCE": TransportMode.TRAIN,
    "NIGHT_RAIL": TransportMode.TRAIN,
    "REGIONAL_FAST_RAIL": TransportMode.TRAIN,
    "REGIONAL_RAIL": TransportMode.TRAIN,
    "SUBURBAN": TransportMode.TRAIN,
    "BUS": TransportMode.BUS,
    "COACH": TransportMode.BUS,
    "TRAM": TransportMode.TRAM,
    "SUBWAY": TransportMode.TRAM,
    "METRO": TransportMode.TRAM,
    "FUNICULAR": TransportMode.TRAM,
    "CABLE_CAR": TransportMode.TRAM,
    "AERIAL_LIFT": TransportMode.TRAM,
    "AREAL_LIFT": TransportMode.TRAM,  # literówka w samym API MOTIS — obsługujemy obie wersje
    "FERRY": TransportMode.FERRY,
    "AIRPLANE": TransportMode.FLIGHT,
    "WALK": TransportMode.WALK,
}


# ---------- Błędy ----------


class TransitousError(Exception):
    """Bazowy błąd klienta — router złapie go jednym `except`."""


class TransitousUnavailableError(TransitousError):
    """Serwer nie odpowiedział, zwrócił błąd albo dane w nieoczekiwanym formacie."""


class PlaceNotFoundError(TransitousError):
    """Geokodowanie nie znalazło żadnego miejsca dla podanego tekstu."""


class UnsupportedModeError(TransitousError):
    """Etap ma tryb transportu, którego nie obsługujemy (np. CAR)."""


# ---------- Modele odpowiedzi MOTIS (tylko pola, których używamy) ----------
# Nigdy nie ufamy danym z zewnętrznego API "na słowo" — Pydantic sprawdza ich kształt.
# Nadmiarowe pola są ignorowane, więc nowe pola w API nas nie zepsują.


class MotisModel(BaseModel):
    # populate_by_name: w kodzie piszemy stop_id, w JSON-ie API jest "stopId" (alias).
    model_config = ConfigDict(populate_by_name=True)


class MotisMatch(MotisModel):
    id: str
    name: str
    type: str
    lat: float
    lon: float


class MotisPlace(MotisModel):
    name: str
    lat: float
    lon: float
    stop_id: str | None = Field(default=None, alias="stopId")


class MotisLeg(MotisModel):
    mode: str
    # "from" to słowo kluczowe Pythona — stąd nazwa from_place i alias.
    from_place: MotisPlace = Field(alias="from")
    to_place: MotisPlace = Field(alias="to")
    start_time: AwareDatetime = Field(alias="startTime")
    end_time: AwareDatetime = Field(alias="endTime")
    # Według specyfikacji: dystans w metrach TYLKO dla etapów nie-transportowych (pieszych).
    distance: float | None = None
    intermediate_stops: list[MotisPlace] = Field(default_factory=list, alias="intermediateStops")


class MotisItinerary(MotisModel):
    transfers: int
    legs: list[MotisLeg]


class MotisPlanResponse(MotisModel):
    itineraries: list[MotisItinerary]


# TypeAdapter waliduje dowolny typ (tu: listę), nie tylko klasy BaseModel.
GEOCODE_RESPONSE_ADAPTER = TypeAdapter(list[MotisMatch])
PLAN_RESPONSE_ADAPTER = TypeAdapter(MotisPlanResponse)


# ---------- Nasze wyniki ----------


@dataclass(frozen=True)
class GeocodedPlace:
    name: str
    coordinates: Coordinates
    stop_id: str | None = None

    def as_motis_place(self) -> str:
        """Format parametru fromPlace/toPlace: ID przystanku albo "lat,lon"."""
        if self.stop_id:
            return self.stop_id
        return f"{self.coordinates.latitude},{self.coordinates.longitude}"


@dataclass(frozen=True)
class RouteOption:
    """Jedna propozycja połączenia: etapy gotowe do zapisu w bazie (LegCreate)."""

    legs: list[LegCreate]
    transfers: int

    @property
    def departure(self) -> datetime:
        return self.legs[0].departure

    @property
    def arrival(self) -> datetime:
        return self.legs[-1].arrival


# ---------- Funkcje pomocnicze ----------


def build_user_agent(app_name: str, app_version: str, contact: str) -> str:
    """Np. "AI-Trip-Planner/0.1.0 (jan@example.com)" — wymóg zasad Transitous."""
    if not contact.strip():
        raise ValueError(
            "Brak APP_CONTACT w .env — Transitous wymaga kontaktu w nagłówku User-Agent"
        )
    product = app_name.strip().replace(" ", "-")
    return f"{product}/{app_version} ({contact.strip()})"


def create_http_client(base_url: str, user_agent: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={"User-Agent": user_agent},
        timeout=DEFAULT_TIMEOUT,
    )


def path_length_km(places: list[MotisPlace]) -> float:
    """Długość trasy po kolejnych punktach: A→B + B→C + ... (w km)."""
    total_km = 0.0
    for start, end in zip(places, places[1:], strict=False):
        total_km += haversine_km(Coordinates(start.lat, start.lon), Coordinates(end.lat, end.lon))
    return total_km


def convert_leg(motis_leg: MotisLeg) -> LegCreate:
    """Etap MOTIS → nasz LegCreate z dystansem i CO₂."""
    mode = MOTIS_MODE_TO_TRANSPORT_MODE.get(motis_leg.mode)
    if mode is None:
        raise UnsupportedModeError(f"Nieobsługiwany tryb transportu: {motis_leg.mode}")

    if mode is TransportMode.WALK and motis_leg.distance is not None:
        distance_km = motis_leg.distance / 1000  # API podaje metry
    else:
        # Dla pociągów/autobusów API nie podaje dystansu — liczymy go po przystankach.
        # Przez przystanki pośrednie wychodzi bliżej prawdziwej trasy niż prosto A→B.
        stops = [motis_leg.from_place, *motis_leg.intermediate_stops, motis_leg.to_place]
        distance_km = path_length_km(stops)

    return LegCreate(
        mode=mode,
        from_place=motis_leg.from_place.name,
        to_place=motis_leg.to_place.name,
        departure=motis_leg.start_time,
        arrival=motis_leg.end_time,
        distance_km=round(distance_km, 3),
        co2_kg=round(estimate_co2_kg(mode, distance_km), 3),
        source=LegSource.TRANSITOUS,
    )


def to_motis_time(moment: datetime) -> str:
    """ISO 8601 w UTC z "Z", np. "2026-11-19T07:00:00Z"."""
    if moment.tzinfo is None:
        raise ValueError("Czas musi mieć strefę czasową (np. datetime(..., tzinfo=UTC))")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ---------- Klient ----------


class TransitousClient:
    def __init__(self, http_client: httpx.Client, cache: ResponseCache | None = None) -> None:
        # Wstrzykujemy gotowego httpx.Client: w testach podajemy klienta z MockTransport,
        # więc żadne zapytanie nie wychodzi do internetu.
        self._http = http_client
        self._cache = cache

    def geocode(self, text: str) -> GeocodedPlace:
        """Tekst (np. "Gdańsk") → najlepiej dopasowane miejsce."""
        query = text.strip()
        if not query:
            raise ValueError("Nazwa miejsca nie może być pusta")

        payload = self._get_json(GEOCODE_PATH, {"text": query, "numResults": 5}, GEOCODE_CACHE_TTL)
        matches = self._parse(GEOCODE_RESPONSE_ADAPTER, payload)
        if not matches:
            raise PlaceNotFoundError(f"Nie znaleziono miejsca: {query}")

        best_match = matches[0]  # API sortuje wyniki od najlepiej dopasowanego
        return GeocodedPlace(
            name=best_match.name,
            coordinates=Coordinates(best_match.lat, best_match.lon),
            stop_id=best_match.id if best_match.type == "STOP" else None,
        )

    def plan(
        self, origin: GeocodedPlace, destination: GeocodedPlace, departure: datetime
    ) -> list[RouteOption]:
        """Połączenia z origin do destination, odjazd nie wcześniej niż `departure`."""
        params = {
            "fromPlace": origin.as_motis_place(),
            "toPlace": destination.as_motis_place(),
            "time": to_motis_time(departure),
            "numItineraries": 5,
            # Bez geometrii tras (polylinii) — nie rysujemy mapy, a odpowiedź jest dużo mniejsza.
            "detailedLegs": False,
            "detailedTransfers": False,
        }
        payload = self._get_json(PLAN_PATH, params, PLAN_CACHE_TTL)
        response = self._parse(PLAN_RESPONSE_ADAPTER, payload)

        options: list[RouteOption] = []
        for itinerary in response.itineraries:
            try:
                legs = [convert_leg(motis_leg) for motis_leg in itinerary.legs]
            # ValueError obejmuje też pydantic.ValidationError (np. przyjazd przed odjazdem)
            # i błędne współrzędne z Coordinates.
            except (UnsupportedModeError, ValueError):
                # Jedna dziwna trasa (np. z samochodem) nie psuje pozostałych — pomijamy ją.
                continue
            if legs:
                options.append(RouteOption(legs=legs, transfers=itinerary.transfers))
        return options

    def _get_json(self, path: str, params: dict[str, Any], ttl: timedelta) -> Any:
        cache_key = make_cache_key(path, params)
        if self._cache is not None:
            cached_payload = self._cache.get(cache_key)
            if cached_payload is not None:
                return cached_payload

        try:
            response = self._http.get(path, params=params)
            response.raise_for_status()  # 4xx/5xx → httpx.HTTPStatusError
            payload = response.json()
        # Kolejność ma znaczenie: TimeoutException dziedziczy po RequestError,
        # więc musi być sprawdzony PIERWSZY, inaczej nigdy by nie "wygrał".
        except httpx.TimeoutException as error:
            raise TransitousUnavailableError("Transitous nie odpowiedział na czas") from error
        except httpx.HTTPStatusError as error:
            raise TransitousUnavailableError(
                f"Transitous zwrócił błąd HTTP {error.response.status_code}"
            ) from error
        except httpx.RequestError as error:
            raise TransitousUnavailableError("Brak połączenia z Transitous") from error
        except ValueError as error:  # response.json() na odpowiedzi, która nie jest JSON-em
            raise TransitousUnavailableError("Transitous zwrócił niepoprawny JSON") from error

        # Zapisujemy tylko udane odpowiedzi — błędu nie chcemy "pamiętać" przez godzinę.
        if self._cache is not None:
            self._cache.set(cache_key, payload, ttl)
        return payload

    # [ParsedT] to składnia generyczna Pythona 3.12: "zwracam ten sam typ, który opisuje
    # adapter" — dla GEOCODE_RESPONSE_ADAPTER list[MotisMatch], dla planu MotisPlanResponse.
    @staticmethod
    def _parse[ParsedT](adapter: TypeAdapter[ParsedT], payload: Any) -> ParsedT:
        try:
            return adapter.validate_python(payload)
        except ValidationError as error:
            raise TransitousUnavailableError(
                "Odpowiedź Transitous ma nieoczekiwany format"
            ) from error
