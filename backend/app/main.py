"""Punkt wejścia aplikacji FastAPI.

Uruchomienie (z katalogu backend/):  fastapi dev app/main.py
Dokumentacja API:                      http://localhost:8000/docs
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import create_db_and_tables, create_db_engine
from app.routers import health, plan, trips
from app.services.cache import ResponseCache
from app.services.intent_parser import create_intent_parser
from app.services.transitous import TransitousClient, build_user_agent, create_http_client

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Buduje aplikację. Testy przekazują własne Settings, produkcja używa .env."""
    settings = settings or get_settings()
    # create_engine nie łączy się jeszcze z bazą — robi to dopiero przy pierwszym zapytaniu.
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Kod przed yield wykonuje się przy starcie serwera, po yield — przy zamykaniu.
        create_db_and_tables(engine)

        # Jeden klient HTTP na cały czas życia aplikacji: ponownie używa połączeń
        # (keep-alive) zamiast otwierać nowe przy każdym requeście.
        transitous_http = None
        try:
            user_agent = build_user_agent(
                settings.app_name, settings.app_version, settings.app_contact
            )
        except ValueError as error:
            # Aplikacja startuje mimo to — CRUD działa, a /api/plan zwróci czytelne 503.
            logger.warning("Wyszukiwanie połączeń wyłączone: %s", error)
        else:
            transitous_http = create_http_client(settings.transitous_base_url, user_agent)
            app.state.route_provider = TransitousClient(transitous_http, ResponseCache(engine))

        yield

        if transitous_http is not None:
            transitous_http.close()
        engine.dispose()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.engine = engine  # get_session() pobiera stąd silnik dla każdego requestu
    app.state.route_provider = None  # ustawiany w lifespan, gdy jest APP_CONTACT
    app.state.intent_parser = create_intent_parser(settings)  # None = brak klucza AI

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
    app.include_router(plan.router)
    return app


app = create_app()
