"""Operacje na bazie dla podróży i etapów. Nic tu nie wie o HTTP.

Funkcje zwracają None, gdy rekordu nie ma — to router decyduje, że oznacza to 404.
"""

from sqlmodel import Session, col, select

from app.models import Leg, LegUpdate, Trip, TripCreate, TripUpdate


class InvalidLegTimesError(ValueError):
    """Po zmianie etapu przyjazd wypadałby przed odjazdem."""


def list_trips(session: Session) -> list[Trip]:
    statement = select(Trip).order_by(col(Trip.created_at).desc())
    return list(session.exec(statement).all())


def get_trip(session: Session, trip_id: int) -> Trip | None:
    return session.get(Trip, trip_id)


def create_trip(session: Session, trip_data: TripCreate) -> Trip:
    # Dane przeszły już walidację w TripCreate/LegCreate. Tworzymy obiekty konstruktorem,
    # bo Leg.model_validate() wymagałby trip_id, którego jeszcze nie ma — baza nada id
    # podróży dopiero przy commit(), a SQLAlchemy wtedy sam uzupełni trip_id w etapach.
    trip = Trip(**trip_data.model_dump(exclude={"legs"}))
    trip.legs = [Leg(**leg_data.model_dump()) for leg_data in trip_data.legs]

    session.add(trip)
    session.commit()
    session.refresh(trip)  # pobiera z bazy nadane id i created_at
    return trip


def update_trip(session: Session, trip: Trip, changes: TripUpdate) -> Trip:
    # exclude_unset=True: tylko pola, które klient faktycznie wysłał.
    for field_name, new_value in changes.model_dump(exclude_unset=True).items():
        setattr(trip, field_name, new_value)

    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip


def delete_trip(session: Session, trip: Trip) -> None:
    session.delete(trip)  # etapy znikają dzięki cascade_delete
    session.commit()


def get_leg_of_trip(session: Session, trip_id: int, leg_id: int) -> Leg | None:
    leg = session.get(Leg, leg_id)
    # Etap musi należeć do TEJ podróży. Bez tego /trips/1/legs/99 zmieniłby etap innej podróży.
    if leg is None or leg.trip_id != trip_id:
        return None
    return leg


def update_leg(session: Session, leg: Leg, changes: LegUpdate) -> Leg:
    new_values = changes.model_dump(exclude_unset=True)

    # Sprawdzamy czasy PO scaleniu: klient mógł zmienić tylko jeden z nich.
    departure = new_values.get("departure", leg.departure)
    arrival = new_values.get("arrival", leg.arrival)
    if arrival < departure:
        raise InvalidLegTimesError("Przyjazd nie może być wcześniejszy niż odjazd")

    for field_name, new_value in new_values.items():
        setattr(leg, field_name, new_value)

    session.add(leg)
    session.commit()
    session.refresh(leg)
    return leg


def delete_leg(session: Session, leg: Leg) -> None:
    session.delete(leg)
    session.commit()
