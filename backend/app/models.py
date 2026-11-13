"""Modele danych: tabele w bazie (table=True) i schematy API (wejście/wyjście).

Układ "Base → Table / Create / Read / Update" to wzorzec z dokumentacji SQLModel:
- *Base   — pola wspólne, z walidacją,
- Trip/Leg (table=True) — tabele w bazie,
- *Create — co klient wysyła przy tworzeniu (bez id, created_at),
- *Read   — co API zwraca,
- *Update — PATCH: wszystkie pola opcjonalne.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, computed_field, model_validator
from sqlmodel import Field, Relationship, SQLModel


class Priority(StrEnum):
    CHEAP = "cheap"
    FAST = "fast"
    GREEN = "green"


class TransportMode(StrEnum):
    TRAIN = "train"
    BUS = "bus"
    FLIGHT = "flight"
    TRAM = "tram"  # tramwaj, metro, kolejka linowa — transport miejski na szynach/linach
    FERRY = "ferry"
    WALK = "walk"  # dojścia i przesiadki piesze z Transitous


class LegSource(StrEnum):
    TRANSITOUS = "transitous"  # prawdziwe dane z rozkładu jazdy
    ESTIMATE = "estimate"  # nasz szacunek (np. loty) — oznaczany w UI


def utc_now() -> datetime:
    return datetime.now(UTC)


def reject_explicit_nulls(model: SQLModel) -> None:
    """PATCH: pole pominięte = "nie zmieniaj", ale jawne null dla wymaganego pola to błąd.

    Bez tego {"name": null} przeszłoby walidację, a baza rzuciłaby błąd NOT NULL (500).
    """
    for field_name in model.model_fields_set:
        if getattr(model, field_name) is None:
            raise ValueError(f"Pole '{field_name}' nie może być null")


# ---------- Leg (etap podróży) ----------


class LegBase(SQLModel):
    mode: TransportMode
    from_place: str = Field(min_length=1, max_length=200)
    to_place: str = Field(min_length=1, max_length=200)
    # AwareDatetime wymaga strefy czasowej (np. "2026-11-19T06:00:00+01:00" albo "...Z").
    # "06:00" bez strefy jest niejednoznaczne: czas Gdańska? Amsterdamu? Baza zapisuje UTC.
    departure: AwareDatetime
    arrival: AwareDatetime
    distance_km: float = Field(ge=0)
    co2_kg: float = Field(ge=0)
    source: LegSource


class Leg(LegBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # ondelete="CASCADE": usunięcie podróży w bazie usuwa też jej etapy.
    trip_id: int = Field(foreign_key="trip.id", ondelete="CASCADE", index=True)

    trip: "Trip" = Relationship(back_populates="legs")


class LegCreate(LegBase):
    @model_validator(mode="after")
    def check_arrival_after_departure(self) -> Self:
        if self.arrival < self.departure:
            raise ValueError("Przyjazd nie może być wcześniejszy niż odjazd")
        return self


class LegRead(LegBase):
    id: int
    trip_id: int


class LegUpdate(SQLModel):
    mode: TransportMode | None = None
    from_place: str | None = Field(default=None, min_length=1, max_length=200)
    to_place: str | None = Field(default=None, min_length=1, max_length=200)
    departure: AwareDatetime | None = None
    arrival: AwareDatetime | None = None
    distance_km: float | None = Field(default=None, ge=0)
    co2_kg: float | None = Field(default=None, ge=0)
    source: LegSource | None = None

    @model_validator(mode="after")
    def check_no_explicit_nulls(self) -> Self:
        reject_explicit_nulls(self)
        return self


# ---------- Trip (podróż) ----------


class TripBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    travel_date: date
    priority: Priority


class Trip(TripBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # default_factory (a nie default=utc_now()) — inaczej każdy Trip dostałby czas startu serwera.
    created_at: datetime = Field(default_factory=utc_now)

    legs: list[Leg] = Relationship(
        back_populates="trip",
        # cascade_delete: ORM usuwa etapy razem z podróżą (session.delete(trip)).
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "Leg.departure"},
    )


class TripCreate(TripBase):
    legs: list[LegCreate] = []


class TripRead(TripBase):
    id: int
    created_at: datetime
    legs: list[LegRead]

    # Sumy liczone w locie z etapów, nie zapisywane w bazie — nie mogą się "rozjechać".
    @computed_field
    @property
    def total_co2_kg(self) -> float:
        return round(sum(leg.co2_kg for leg in self.legs), 3)

    @computed_field
    @property
    def total_distance_km(self) -> float:
        return round(sum(leg.distance_km for leg in self.legs), 3)


class TripUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    origin: str | None = Field(default=None, min_length=1, max_length=200)
    destination: str | None = Field(default=None, min_length=1, max_length=200)
    travel_date: date | None = None
    priority: Priority | None = None

    @model_validator(mode="after")
    def check_no_explicit_nulls(self) -> Self:
        reject_explicit_nulls(self)
        return self


# ---------- Plan (POST /api/plan) — tylko schematy API, bez tabel ----------


class PlanRequest(SQLModel):
    """Albo zdanie dla AI (`query`), albo pola formularza — nigdy oba naraz."""

    # Luźny limit chroni przed ogromnym body; dokładny (300 znaków po oczyszczeniu
    # spacji) sprawdza parser intencji.
    query: str | None = Field(default=None, max_length=1000)
    origin: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=200)
    travel_date: date | None = None
    priority: Priority | None = None

    @model_validator(mode="after")
    def check_query_or_form(self) -> Self:
        form_values = (self.origin, self.destination, self.travel_date, self.priority)
        if self.query is not None:
            if any(value is not None for value in form_values):
                raise ValueError("Podaj zapytanie (query) albo pola formularza — nie oba naraz")
        elif self.origin is None or self.destination is None or self.travel_date is None:
            raise ValueError("Formularz wymaga pól origin, destination i travel_date")
        return self


class PlanOption(SQLModel):
    """Jedna propozycja trasy. `legs` mają format LegCreate — frontend może je od razu
    wysłać do POST /api/trips, żeby zapisać plan."""

    legs: list[LegCreate]
    transfers: int = Field(ge=0)
    departure: AwareDatetime
    arrival: AwareDatetime
    duration_minutes: int = Field(ge=0)
    total_distance_km: float = Field(ge=0)
    total_co2_kg: float = Field(ge=0)
    estimated_cost_eur: float = Field(ge=0)  # zawsze szacunek — Transitous nie zna cen
    is_estimate: bool  # True, gdy któryś etap to nasz szacunek (lot)
    recommended: bool = False


class PlanResponse(SQLModel):
    origin: str
    destination: str
    origin_name: str  # nazwa znaleziona przez geokodowanie, np. "Gdańsk Główny"
    destination_name: str
    travel_date: date
    priority: Priority
    parsed_by: Literal["ai", "form"]
    options: list[PlanOption]  # posortowane według priorytetu; pierwsza = rekomendacja
    recommendation: str | None
    warnings: list[str]
    data_sources_url: str
