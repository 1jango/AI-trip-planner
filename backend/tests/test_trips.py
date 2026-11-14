from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.emissions import EMISSION_FACTORS_KG_PER_PASSENGER_KM


def make_leg_payload(**overrides: Any) -> dict[str, Any]:
    leg = {
        "mode": "train",
        "from_place": "Gdańsk Główny",
        "to_place": "Berlin Hbf",
        "departure": "2026-11-19T06:00:00+01:00",
        "arrival": "2026-11-19T12:30:00+01:00",
        "distance_km": 520.0,
        "co2_kg": 15.6,
        "source": "transitous",
    }
    leg.update(overrides)
    return leg


def make_trip_payload(**overrides: Any) -> dict[str, Any]:
    trip = {
        "name": "Konferencja",
        "origin": "Gdańsk",
        "destination": "'s-Hertogenbosch",
        "travel_date": "2026-11-19",
        "priority": "cheap",
        "legs": [
            make_leg_payload(),
            make_leg_payload(
                from_place="Berlin Hbf",
                to_place="'s-Hertogenbosch",
                departure="2026-11-19T13:00:00+01:00",
                arrival="2026-11-19T19:00:00+01:00",
                distance_km=650.0,
                co2_kg=19.5,
            ),
        ],
    }
    trip.update(overrides)
    return trip


@pytest.fixture
def created_trip(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/trips", json=make_trip_payload())
    assert response.status_code == 201
    return response.json()


# ---------- POST /api/trips ----------


def test_create_trip_returns_201_with_ids_and_totals(client: TestClient) -> None:
    response = client.post("/api/trips", json=make_trip_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"] is not None
    assert body["created_at"] is not None
    assert len(body["legs"]) == 2
    assert all(leg["trip_id"] == body["id"] for leg in body["legs"])
    assert body["total_co2_kg"] == pytest.approx(35.1)
    assert body["total_distance_km"] == pytest.approx(1170.0)


def test_create_trip_without_legs_has_zero_totals(client: TestClient) -> None:
    response = client.post("/api/trips", json=make_trip_payload(legs=[]))

    assert response.status_code == 201
    assert response.json()["total_co2_kg"] == 0


def test_create_trip_returns_legs_sorted_by_departure(client: TestClient) -> None:
    later_leg, earlier_leg = make_trip_payload()["legs"][1], make_trip_payload()["legs"][0]

    response = client.post("/api/trips", json=make_trip_payload(legs=[later_leg, earlier_leg]))

    departures = [leg["departure"] for leg in response.json()["legs"]]
    assert departures == sorted(departures)


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"name": ""},
        {"priority": "luxury"},
        {"travel_date": "not-a-date"},
        {"legs": [make_leg_payload(distance_km=-5)]},
        {"legs": [make_leg_payload(mode="teleport")]},
        {"legs": [make_leg_payload(arrival="2026-11-19T05:00:00+01:00")]},  # przed odjazdem
    ],
)
def test_create_trip_with_invalid_data_returns_422(
    client: TestClient, invalid_fields: dict[str, Any]
) -> None:
    response = client.post("/api/trips", json=make_trip_payload(**invalid_fields))

    assert response.status_code == 422


def test_create_trip_with_missing_field_returns_422(client: TestClient) -> None:
    payload = make_trip_payload()
    del payload["origin"]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 422


# ---------- GET /api/trips, GET /api/trips/{id} ----------


def test_list_trips_is_empty_on_fresh_database(client: TestClient) -> None:
    response = client.get("/api/trips")

    assert response.status_code == 200
    assert response.json() == []


def test_list_trips_returns_newest_first(client: TestClient) -> None:
    client.post("/api/trips", json=make_trip_payload(name="Pierwsza"))
    client.post("/api/trips", json=make_trip_payload(name="Druga"))

    names = [trip["name"] for trip in client.get("/api/trips").json()]

    assert names == ["Druga", "Pierwsza"]


def test_read_trip_returns_trip_with_legs(client: TestClient, created_trip: dict[str, Any]) -> None:
    response = client.get(f"/api/trips/{created_trip['id']}")

    assert response.status_code == 200
    assert response.json() == created_trip


def test_read_missing_trip_returns_404(client: TestClient) -> None:
    response = client.get("/api/trips/999")

    assert response.status_code == 404


# ---------- PATCH /api/trips/{id} ----------


def test_patch_trip_changes_only_sent_fields(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    response = client.patch(f"/api/trips/{created_trip['id']}", json={"name": "Nowa nazwa"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nowa nazwa"
    assert body["origin"] == created_trip["origin"]
    assert body["priority"] == created_trip["priority"]
    assert len(body["legs"]) == 2


def test_patch_trip_with_explicit_null_returns_422(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    response = client.patch(f"/api/trips/{created_trip['id']}", json={"name": None})

    assert response.status_code == 422


def test_patch_trip_with_invalid_priority_returns_422(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    response = client.patch(f"/api/trips/{created_trip['id']}", json={"priority": "luxury"})

    assert response.status_code == 422


def test_patch_missing_trip_returns_404(client: TestClient) -> None:
    response = client.patch("/api/trips/999", json={"name": "X"})

    assert response.status_code == 404


# ---------- DELETE /api/trips/{id} ----------


def test_delete_trip_returns_204_and_removes_it(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    response = client.delete(f"/api/trips/{created_trip['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/trips/{created_trip['id']}").status_code == 404


def test_delete_trip_also_deletes_its_legs(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    trip_id = created_trip["id"]
    leg_id = created_trip["legs"][0]["id"]

    client.delete(f"/api/trips/{trip_id}")

    assert client.patch(f"/api/trips/{trip_id}/legs/{leg_id}", json={}).status_code == 404


def test_delete_missing_trip_returns_404(client: TestClient) -> None:
    response = client.delete("/api/trips/999")

    assert response.status_code == 404


# ---------- PATCH /api/trips/{id}/legs/{leg_id} ----------


def test_patch_leg_changes_only_sent_fields(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    leg = created_trip["legs"][0]

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}", json={"mode": "bus", "co2_kg": 9.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "bus"
    assert body["co2_kg"] == 9.0
    assert body["from_place"] == leg["from_place"]


def test_patch_leg_mode_recomputes_co2_and_marks_estimate(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    leg = created_trip["legs"][0]  # pociąg, 520 km, 15.6 kg (wartość z payloadu testowego)

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}", json={"mode": "bus"}
    )

    body = response.json()
    assert body["co2_kg"] == pytest.approx(
        520.0 * EMISSION_FACTORS_KG_PER_PASSENGER_KM["bus"], abs=0.001
    )
    assert body["source"] == "estimate"


def test_patch_leg_distance_recomputes_co2_but_keeps_source(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    leg = created_trip["legs"][0]

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}", json={"distance_km": 100.0}
    )

    body = response.json()
    assert body["co2_kg"] == pytest.approx(
        100.0 * EMISSION_FACTORS_KG_PER_PASSENGER_KM["train"], abs=0.001
    )
    assert body["source"] == "transitous"


def test_patch_leg_times_only_keeps_co2(client: TestClient, created_trip: dict[str, Any]) -> None:
    leg = created_trip["legs"][0]

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}",
        json={"arrival": "2026-11-19T12:45:00+01:00"},
    )

    assert response.json()["co2_kg"] == leg["co2_kg"]


def test_patch_leg_updates_trip_total(client: TestClient, created_trip: dict[str, Any]) -> None:
    leg = created_trip["legs"][0]

    client.patch(f"/api/trips/{created_trip['id']}/legs/{leg['id']}", json={"co2_kg": 0.5})

    trip = client.get(f"/api/trips/{created_trip['id']}").json()
    assert trip["total_co2_kg"] == pytest.approx(0.5 + 19.5)


def test_patch_leg_arrival_before_existing_departure_returns_422(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    leg = created_trip["legs"][0]  # odjazd 06:00

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}",
        json={"arrival": "2026-11-19T05:00:00+01:00"},
    )

    assert response.status_code == 422


def test_patch_leg_with_explicit_null_returns_422(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    leg = created_trip["legs"][0]

    response = client.patch(
        f"/api/trips/{created_trip['id']}/legs/{leg['id']}", json={"mode": None}
    )

    assert response.status_code == 422


def test_patch_leg_of_another_trip_returns_404(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    other_trip = client.post("/api/trips", json=make_trip_payload(name="Inna")).json()
    leg_of_first_trip = created_trip["legs"][0]

    response = client.patch(
        f"/api/trips/{other_trip['id']}/legs/{leg_of_first_trip['id']}", json={"mode": "bus"}
    )

    assert response.status_code == 404


# ---------- DELETE /api/trips/{id}/legs/{leg_id} ----------


def test_delete_leg_returns_204_and_keeps_other_legs(
    client: TestClient, created_trip: dict[str, Any]
) -> None:
    removed_leg, remaining_leg = created_trip["legs"]

    response = client.delete(f"/api/trips/{created_trip['id']}/legs/{removed_leg['id']}")

    assert response.status_code == 204
    trip = client.get(f"/api/trips/{created_trip['id']}").json()
    assert [leg["id"] for leg in trip["legs"]] == [remaining_leg["id"]]
    assert trip["total_co2_kg"] == pytest.approx(remaining_leg["co2_kg"])


def test_delete_missing_leg_returns_404(client: TestClient, created_trip: dict[str, Any]) -> None:
    response = client.delete(f"/api/trips/{created_trip['id']}/legs/999")

    assert response.status_code == 404


# ---------- Strefy czasowe ----------


def test_create_leg_without_timezone_returns_422(client: TestClient) -> None:
    naive_leg = make_leg_payload(departure="2026-11-19T06:00:00", arrival="2026-11-19T12:30:00")

    response = client.post("/api/trips", json=make_trip_payload(legs=[naive_leg]))

    assert response.status_code == 422


def test_leg_times_are_returned_in_utc(client: TestClient) -> None:
    leg = make_leg_payload(departure="2026-11-19T06:00:00+01:00")

    response = client.post("/api/trips", json=make_trip_payload(legs=[leg]))

    returned_departure = response.json()["legs"][0]["departure"]
    assert datetime.fromisoformat(returned_departure) == datetime(2026, 11, 19, 5, 0, tzinfo=UTC)
