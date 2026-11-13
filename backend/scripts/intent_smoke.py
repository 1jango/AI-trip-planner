"""Ręczny test parsera na PRAWDZIWYM API Groq (1 zapytanie na zdanie).

Wymaga GROQ_API_KEY w .env. Uruchomienie z katalogu backend/:

    python -m scripts.intent_smoke
    python -m scripts.intent_smoke "z Gdyni do Wrocławia jutro, ekologicznie"
"""

import sys
from datetime import date

from app.config import get_settings
from app.services.intent_parser import IntentParserError, create_intent_parser

DEFAULT_QUERIES = (
    "Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej",
    "z Gdyni do Wrocławia jutro, jak najszybciej",
    "Berlin to Amsterdam on Saturday, lowest emissions",
    "chcę gdzieś pojechać",  # celowo niepełne — oczekujemy czytelnego błędu
)


def main() -> int:
    parser = create_intent_parser(get_settings())
    if parser is None:
        print("AI niedostępne: ustaw GROQ_API_KEY w pliku .env w katalogu głównym repo.")
        return 1

    queries = sys.argv[1:] or DEFAULT_QUERIES
    today = date.today()
    print(f"Dzisiaj: {today:%Y-%m-%d (%A)}\n")
    for query in queries:
        print(f"> {query}")
        try:
            intent = parser.parse(query, today)
        except IntentParserError as error:
            print(f"  {type(error).__name__}: {error}\n")
            continue
        print(
            f"  {intent.origin} → {intent.destination}, "
            f"{intent.travel_date:%Y-%m-%d (%A)}, priorytet: {intent.priority}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
