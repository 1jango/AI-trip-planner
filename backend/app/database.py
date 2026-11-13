"""Połączenie z bazą SQLite i sesje dla endpointów."""

from collections.abc import Iterator
from sqlite3 import Connection as SQLiteConnection

from fastapi import Request
from sqlalchemy import Engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def create_db_engine(database_url: str) -> Engine:
    """Tworzy silnik bazy. "sqlite://" (bez ścieżki) oznacza bazę w pamięci — używaną w testach."""
    is_in_memory = database_url in ("sqlite://", "sqlite:///:memory:")

    engine = create_engine(
        database_url,
        # FastAPI obsługuje requesty w wielu wątkach, a sqlite3 domyślnie na to nie pozwala.
        connect_args={"check_same_thread": False},
        # Baza w pamięci istnieje tylko w ramach JEDNEGO połączenia. StaticPool sprawia,
        # że wszystkie sesje używają tego samego połączenia — inaczej każda widziałaby pustą bazę.
        poolclass=StaticPool if is_in_memory else None,
    )

    # SQLite domyślnie IGNORUJE klucze obce (w tym ON DELETE CASCADE).
    # Trzeba je włączyć osobno dla każdego nowego połączenia.
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: SQLiteConnection, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_db_and_tables(engine: Engine) -> None:
    # Import rejestruje modele w SQLModel.metadata — bez niego create_all nie zna tabel.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session(request: Request) -> Iterator[Session]:
    """Zależność FastAPI: jedna sesja na request, zamykana automatycznie po odpowiedzi."""
    with Session(request.app.state.engine) as session:
        yield session
