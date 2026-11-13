"""Endpoint sprawdzający, czy backend działa i czy AI jest dostępne."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    ai_available: bool


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        ai_available=settings.ai_available,
    )
