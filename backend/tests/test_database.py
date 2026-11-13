from sqlalchemy import text
from sqlmodel import Session

from app.database import create_db_and_tables, create_db_engine


def test_sqlite_enforces_foreign_keys_and_cascade() -> None:
    """Bez PRAGMA foreign_keys=ON SQLite zostawiłby "osierocone" etapy."""
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)

    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO trip"
                " (id, name, origin, destination, travel_date, priority, created_at)"
                " VALUES (1, 'T', 'A', 'B', '2026-11-19', 'CHEAP', '2026-11-13 10:00:00')"
            )
        )
        session.execute(
            text(
                "INSERT INTO leg (id, trip_id, mode, from_place, to_place, departure, arrival,"
                " distance_km, co2_kg, source) VALUES (1, 1, 'TRAIN', 'A', 'B',"
                " '2026-11-19 06:00:00', '2026-11-19 08:00:00', 100, 3, 'TRANSITOUS')"
            )
        )
        # Surowy SQL omija ORM — sprawdzamy, że kaskadę wykonuje sama baza.
        session.execute(text("DELETE FROM trip WHERE id = 1"))
        remaining_legs = session.execute(text("SELECT COUNT(*) FROM leg")).scalar_one()

    assert remaining_legs == 0
