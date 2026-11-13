"""Ręczny test na PRAWDZIWYM API Transitous (3 zapytania; powtórki idą z cache).

Wymaga APP_CONTACT w .env (kontakt trafia do nagłówka User-Agent).
Uruchomienie z katalogu backend/:

    python -m scripts.transitous_smoke
    python -m scripts.transitous_smoke "Gdańsk" "'s-Hertogenbosch"
"""

import sys
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.database import create_db_and_tables, create_db_engine
from app.services.cache import ResponseCache
from app.services.transitous import (
    TRANSITOUS_SOURCES_URL,
    TransitousClient,
    TransitousError,
    build_user_agent,
    create_http_client,
)


def next_weekday_morning(weekday: int, hour_utc: int = 7) -> datetime:
    """Najbliższy dany dzień tygodnia (0 = poniedziałek) o podanej godzinie UTC."""
    today = datetime.now(UTC).replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    days_ahead = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def main() -> int:
    origin_text = sys.argv[1] if len(sys.argv) > 1 else "Gdańsk"
    destination_text = sys.argv[2] if len(sys.argv) > 2 else "'s-Hertogenbosch"

    settings = get_settings()
    try:
        user_agent = build_user_agent(settings.app_name, settings.app_version, settings.app_contact)
    except ValueError as error:
        print(f"Błąd konfiguracji: {error}")
        return 1

    engine = create_db_engine(settings.database_url)
    create_db_and_tables(engine)
    departure = next_weekday_morning(weekday=3)  # czwartek

    with create_http_client(settings.transitous_base_url, user_agent) as http_client:
        client = TransitousClient(http_client, cache=ResponseCache(engine))
        try:
            origin = client.geocode(origin_text)
            destination = client.geocode(destination_text)
            print(f"Skąd:  {origin}\nDokąd: {destination}\nOdjazd od: {departure}\n")
            options = client.plan(origin, destination, departure)
        except TransitousError as error:
            print(f"Transitous: {error}")
            return 1

    if not options:
        print("Brak połączeń w tym oknie czasowym.")
    for number, option in enumerate(options, start=1):
        total_co2 = sum(leg.co2_kg for leg in option.legs)
        total_km = sum(leg.distance_km for leg in option.legs)
        print(
            f"#{number}: {option.departure:%H:%M} → {option.arrival:%H:%M} UTC, "
            f"przesiadki: {option.transfers}, {total_km:.0f} km, {total_co2:.1f} kg CO₂e"
        )
        for leg in option.legs:
            print(
                f"    {leg.mode:<6} {leg.from_place} → {leg.to_place} "
                f"({leg.distance_km:.1f} km, {leg.co2_kg:.2f} kg)"
            )
    print(f"\nDane: Transitous — {TRANSITOUS_SOURCES_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
