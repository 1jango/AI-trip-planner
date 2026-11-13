import math
from datetime import timedelta

import pytest

from app.models import TransportMode
from app.services.emissions import (
    EARTH_RADIUS_KM,
    EMISSION_FACTORS_KG_PER_PASSENGER_KM,
    Coordinates,
    estimate_co2_kg,
    estimate_flight_duration,
    haversine_km,
)

GDANSK_AIRPORT = Coordinates(latitude=54.3776, longitude=18.4662)
EINDHOVEN_AIRPORT = Coordinates(latitude=51.4501, longitude=5.3745)
PARIS = Coordinates(latitude=48.8566, longitude=2.3522)
LONDON = Coordinates(latitude=51.5074, longitude=-0.1278)


# ---------- haversine_km ----------
# Wartości oczekiwane wynikają z geometrii (nie z naszego kodu), więc test ma sens.


def test_distance_to_same_point_is_zero() -> None:
    assert haversine_km(PARIS, PARIS) == 0


def test_one_degree_of_longitude_on_equator() -> None:
    # Obwód równika / 360 = 2πR / 360 ≈ 111,19 km
    expected_km = 2 * math.pi * EARTH_RADIUS_KM / 360

    distance = haversine_km(Coordinates(0, 0), Coordinates(0, 1))

    assert distance == pytest.approx(expected_km)


def test_pole_to_pole_is_half_circumference() -> None:
    distance = haversine_km(Coordinates(90, 0), Coordinates(-90, 0))

    assert distance == pytest.approx(math.pi * EARTH_RADIUS_KM)


def test_antipodal_points_do_not_crash_on_rounding() -> None:
    # Bez min(1.0, a) błąd zaokrągleń mógłby dać math.asin(1.0000000000000002) → ValueError.
    distance = haversine_km(Coordinates(0, 0), Coordinates(0, 180))

    assert distance == pytest.approx(math.pi * EARTH_RADIUS_KM)


def test_paris_to_london_matches_known_distance() -> None:
    # Powszechnie podawany dystans ortodromy Paryż–Londyn: ok. 343–344 km.
    assert haversine_km(PARIS, LONDON) == pytest.approx(343.5, abs=1.0)


def test_distance_is_symmetric() -> None:
    there = haversine_km(GDANSK_AIRPORT, EINDHOVEN_AIRPORT)
    back = haversine_km(EINDHOVEN_AIRPORT, GDANSK_AIRPORT)

    assert there == pytest.approx(back)


def test_gdansk_to_eindhoven_is_plausible() -> None:
    # Ok. 900 km w linii prostej — sprawdzamy rząd wielkości, nie co do metra.
    assert 850 < haversine_km(GDANSK_AIRPORT, EINDHOVEN_AIRPORT) < 950


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181), (math.nan, 0), (0, math.inf)],
)
def test_invalid_coordinates_raise_value_error(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError):
        Coordinates(latitude, longitude)


# ---------- estimate_co2_kg ----------


def test_every_transport_mode_has_emission_factor() -> None:
    # Strażnik: dodanie nowego TransportMode bez współczynnika wywali ten test,
    # a nie dopiero aplikację u użytkownika (KeyError).
    assert set(EMISSION_FACTORS_KG_PER_PASSENGER_KM) == set(TransportMode)


@pytest.mark.parametrize(
    ("mode", "distance_km", "expected_kg"),
    [
        (TransportMode.TRAIN, 100, 3.546),
        (TransportMode.BUS, 100, 2.776),
        (TransportMode.FLIGHT, 1000, 142.53),
    ],
)
def test_co2_is_distance_times_factor(
    mode: TransportMode, distance_km: float, expected_kg: float
) -> None:
    assert estimate_co2_kg(mode, distance_km) == pytest.approx(expected_kg)


def test_zero_distance_emits_nothing() -> None:
    assert estimate_co2_kg(TransportMode.FLIGHT, 0) == 0


def test_train_emits_less_than_flight_on_same_distance() -> None:
    train = estimate_co2_kg(TransportMode.TRAIN, 900)
    flight = estimate_co2_kg(TransportMode.FLIGHT, 900)

    assert train < flight


@pytest.mark.parametrize("invalid_distance", [-1, math.nan, math.inf])
def test_co2_rejects_invalid_distance(invalid_distance: float) -> None:
    with pytest.raises(ValueError):
        estimate_co2_kg(TransportMode.TRAIN, invalid_distance)


# ---------- estimate_flight_duration ----------


def test_flight_duration_is_cruise_time_plus_overhead() -> None:
    # 800 km przy 800 km/h = 1 h, plus 30 min narzutu
    assert estimate_flight_duration(800) == timedelta(hours=1, minutes=30)


def test_zero_distance_flight_still_has_overhead() -> None:
    assert estimate_flight_duration(0) == timedelta(minutes=30)


def test_flight_duration_rejects_negative_distance() -> None:
    with pytest.raises(ValueError):
        estimate_flight_duration(-100)
