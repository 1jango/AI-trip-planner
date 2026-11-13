"""Punkt wejścia aplikacji FastAPI.

Uruchomienie (z katalogu backend/):  fastapi dev app/main.py
Dokumentacja API:                      http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Buduje aplikację. Testy przekazują własne Settings, produkcja używa .env."""
    settings = settings or get_settings()

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # CORS: przeglądarka pozwoli wołać API tylko stronie z tych originów (frontend Vite).
    # Nie używamy allow_origins=["*"] — to wygodne, ale otwiera API dla każdej strony.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health.router)
    return app


app = create_app()
