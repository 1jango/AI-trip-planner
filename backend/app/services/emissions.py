"""Dystans, emisje CO₂ i szacunkowy czas lotu — czyste funkcje.

"Czyste" znaczy: bez bazy, sieci i stanu globalnego. Ten sam input zawsze daje ten sam
output, więc łatwo je testować i można im ufać przy sortowaniu i rekomendacji.

ŹRÓDŁO WSPÓŁCZYNNIKÓW CO₂
UK Government GHG Conversion Factors for Company Reporting 2025 (DESNZ), plik
"ghg-conversion-factors-2025-flat-format.xlsx", wartości "kg CO2e" na "passenger.km":
https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025
"""

import math
from dataclasses import dataclass
from datetime import timedelta

from app.models import TransportMode

# Średni promień Ziemi (IUGG). Ziemia nie jest idealną kulą — błąd haversine to ok. 0,5%,
# czyli dużo mniej niż niepewność samych współczynników emisji.
EARTH_RADIUS_KM = 6371.0

# kg CO₂e na pasażerokilometr (DESNZ 2025, arkusze "Business travel- land/air").
EMISSION_FACTORS_KG_PER_PASSENGER_KM: dict[TransportMode, float] = {
    # "Rail > National rail" (ID 25_315_3147_11_1). Średnia dla kolei w UK — używamy jej
    # jako przybliżenia dla Europy; realna wartość zależy od miksu energii w danym kraju.
    TransportMode.TRAIN: 0.03546,
    # "Bus > Coach" (ID 25_314_3146_11_1). Autobus dalekobieżny — nasza aplikacja planuje
    # podróże między miastami. Dla porównania: autobus miejski ("Average local bus") = 0.10385.
    TransportMode.BUS: 0.02776,
    # "Flights > International, to/from non-UK > Average passenger > With RF"
    # (ID 21_316_3178_11_1). "With RF" (radiative forcing) uwzględnia dodatkowy wpływ lotu
    # na klimat poza samym CO₂ (smugi kondensacyjne, NOx) — DESNZ zaleca wersję z RF.
    # Współczynnik ZAWIERA już 8% dopłaty do dystansu (okrężne trasy, krążenie przed
    # lądowaniem), więc mnożymy go przez czysty dystans haversine — bez własnych dopłat.
    TransportMode.FLIGHT: 0.14253,
}

# Szacunek czasu lotu — NASZE ZAŁOŻENIA (nie z DESNZ), dlatego wynik ma source="estimate".
# Średnia prędkość "od bramki do bramki" jest niższa niż przelotowa (~850 km/h),
# bo obejmuje wznoszenie i podejście do lądowania.
FLIGHT_AVERAGE_SPEED_KMH = 800.0
# Stały narzut na kołowanie, start i lądowanie — niezależny od dystansu.
FLIGHT_TAXI_AND_TAKEOFF_OVERHEAD = timedelta(minutes=30)


@dataclass(frozen=True)
class Coordinates:
    """Punkt na Ziemi w stopniach. frozen=True: obiekt jest niezmienny (jak krotka)."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        # Sam zakres odrzuciłby też NaN (każde porównanie z NaN daje False) i inf,
        # ale math.isfinite mówi to wprost — czytelnik nie musi znać tej ciekawostki.
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError(f"Szerokość geograficzna poza zakresem [-90, 90]: {self.latitude}")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError(f"Długość geograficzna poza zakresem [-180, 180]: {self.longitude}")


def haversine_km(start: Coordinates, end: Coordinates) -> float:
    """Dystans po powierzchni kuli (ortodroma, "w linii prostej" dla samolotu) w km."""
    # Funkcje trygonometryczne w Pythonie przyjmują RADIANY, nie stopnie.
    start_lat = math.radians(start.latitude)
    end_lat = math.radians(end.latitude)
    delta_lat = math.radians(end.latitude - start.latitude)
    delta_lon = math.radians(end.longitude - start.longitude)

    # Wzór haversine: a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(start_lat) * math.cos(end_lat) * math.sin(delta_lon / 2) ** 2
    )
    # min(1.0, ...) chroni przed błędem zaokrągleń: dla punktów antypodycznych `a` może
    # wyjść 1.0000000000000002, a math.asin(>1) rzuca ValueError.
    central_angle = 2 * math.asin(math.sqrt(min(1.0, a)))
    return EARTH_RADIUS_KM * central_angle


def estimate_co2_kg(mode: TransportMode, distance_km: float) -> float:
    """Emisja CO₂e jednego pasażera na danym dystansie."""
    if not math.isfinite(distance_km) or distance_km < 0:
        raise ValueError(f"Dystans musi być nieujemną liczbą, otrzymano: {distance_km}")
    return distance_km * EMISSION_FACTORS_KG_PER_PASSENGER_KM[mode]


def estimate_flight_duration(distance_km: float) -> timedelta:
    """Szacunkowy czas lotu (od bramki do bramki), bez odprawy na lotnisku."""
    if not math.isfinite(distance_km) or distance_km < 0:
        raise ValueError(f"Dystans musi być nieujemną liczbą, otrzymano: {distance_km}")
    flight_time = timedelta(hours=distance_km / FLIGHT_AVERAGE_SPEED_KMH)
    return flight_time + FLIGHT_TAXI_AND_TAKEOFF_OVERHEAD
