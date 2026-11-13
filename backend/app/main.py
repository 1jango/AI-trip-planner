"""Punkt wejścia aplikacji FastAPI.

Uruchomienie (z katalogu backend/):  fastapi dev app/main.py
Dokumentacja API:                      http://localhost:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import create_db_and_tables, create_db_engine
from app.routers import health, trips


def create_app(settings: Settings | None = None) -> FastAPI:
    """Buduje aplikację. Testy przekazują własne Settings, produkcja używa .env."""
    settings = settings or get_settings()
    # create_engine nie łączy się jeszcze z bazą — robi to dopiero przy pierwszym zapytaniu.
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Kod przed yield wykonuje się przy starcie serwera, po yield — przy zamykaniu.
        create_db_and_tables(engine)
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.engine = engine  # get_session() pobiera stąd silnik dla każdego requestu

    # CORS: przeglądarka pozwoli wołać API tylko stronie z tych originów (frontend Vite).
    # Nie używamy allow_origins=["*"] — to wygodne, ale otwiera API dla każdej strony.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health.router)
    app.include_router(trips.router)
    return app


app = create_app()
