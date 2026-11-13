"""Endpointy REST dla zapisanych podróży. Tylko warstwa HTTP — logika jest w services/trips.py."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.database import get_session
from app.models import Leg, LegRead, LegUpdate, Trip, TripCreate, TripRead, TripUpdate
from app.services import trips as trip_service

router = APIRouter(prefix="/api/trips", tags=["trips"])


def get_trip_or_404(trip_id: int, session: Session = Depends(get_session)) -> Trip:
    trip = trip_service.get_trip(session, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


def get_leg_or_404(trip_id: int, leg_id: int, session: Session = Depends(get_session)) -> Leg:
    leg = trip_service.get_leg_of_trip(session, trip_id, leg_id)
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leg not found")
    return leg


# Konwertujemy do *Read jeszcze w endpoincie, póki sesja jest otwarta —
# relacja trip.legs ładuje się leniwie i po zamknięciu sesji nie byłoby jej skąd pobrać.


@router.get("", response_model=list[TripRead])
def list_trips(session: Session = Depends(get_session)) -> list[TripRead]:
    return [TripRead.model_validate(trip) for trip in trip_service.list_trips(session)]


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(trip_data: TripCreate, session: Session = Depends(get_session)) -> TripRead:
    trip = trip_service.create_trip(session, trip_data)
    return TripRead.model_validate(trip)


@router.get("/{trip_id}", response_model=TripRead)
def read_trip(trip: Trip = Depends(get_trip_or_404)) -> TripRead:
    return TripRead.model_validate(trip)


@router.patch("/{trip_id}", response_model=TripRead)
def update_trip(
    changes: TripUpdate,
    trip: Trip = Depends(get_trip_or_404),
    session: Session = Depends(get_session),
) -> TripRead:
    updated_trip = trip_service.update_trip(session, trip, changes)
    return TripRead.model_validate(updated_trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip: Trip = Depends(get_trip_or_404), session: Session = Depends(get_session)
) -> Response:
    trip_service.delete_trip(session, trip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)  # 204 = sukces, bez body


@router.patch("/{trip_id}/legs/{leg_id}", response_model=LegRead)
def update_leg(
    changes: LegUpdate,
    leg: Leg = Depends(get_leg_or_404),
    session: Session = Depends(get_session),
) -> LegRead:
    try:
        updated_leg = trip_service.update_leg(session, leg, changes)
    except trip_service.InvalidLegTimesError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return LegRead.model_validate(updated_leg)


@router.delete("/{trip_id}/legs/{leg_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_leg(
    leg: Leg = Depends(get_leg_or_404), session: Session = Depends(get_session)
) -> Response:
    trip_service.delete_leg(session, leg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
