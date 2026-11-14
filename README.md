# AI Trip Planner

Wpisz podróż jednym zdaniem, np. **„Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej”**,
a aplikacja pokaże prawdziwe połączenia (pociąg, autobus, tramwaj, prom) i szacunkowy lot,
każde z czasem, emisją CO₂ i orientacyjnym kosztem, oraz poleci jedną opcję. Wybrane plany
można zapisywać, przeglądać, edytować i usuwać.

Projekt powstał jako zadanie rekrutacyjne na staż w Xelerit (Gdańsk).

![Demo](docs/demo.gif)
<!-- Nagraj krótkie demo (np. Kap lub QuickTime → GIF) i zapisz jako docs/demo.gif -->

## Najważniejsza zasada: AI nie wymyśla danych

```
„Gdańsk → Berlin jutro, ekologicznie”
        │
        ▼  LLM (Groq, strict JSON Schema) — TYLKO ekstrakcja
{ origin, destination, travel_date, priority }  ← walidacja Pydantic + reguły biznesowe
        │
        ▼  Transitous (MOTIS 2) — prawdziwe rozkłady jazdy
połączenia + szacunek lotu (haversine)
        │
        ▼  deterministyczny, przetestowany kod
CO₂ (DESNZ 2025) · czas · koszt · ranking wg priorytetu · rekomendacja
```

Model językowy tylko zamienia zdanie na cztery pola. Połączenia, emisje, ranking i rekomendację
liczy zwykły kod, który ma testy. Bez klucza API aplikacja działa dalej: pokazuje zwykły formularz
i plakietkę „AI niedostępne”.

## Stack

| Warstwa | Technologie |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel + SQLite, httpx, pydantic-settings |
| AI | Groq przez SDK `openai`, model `openai/gpt-oss-120b`, structured outputs (strict) |
| Dane | [Transitous](https://transitous.org) (MOTIS 2): geokodowanie i rozkłady jazdy |
| Frontend | React 19, TypeScript (strict, bez `any`), Vite |
| Jakość | pytest (203 testy), ruff, Vitest (33 testy), ESLint |
| Środowisko | conda (`environment.yml`, conda-forge): Python i Node.js w jednym środowisku |

## Ciekawsze rozwiązania

**Kalendarz w prompcie.** LLM-y słabo liczą daty. Zamiast prosić model o wyliczenie, który dzień
to „przyszły czwartek”, dajemy mu gotową listę `2026-11-19 Thursday` na 21 dni. Model tylko
odczytuje datę, a `today` jest parametrem, więc testy dają ten sam wynik każdego dnia.

**Pola nullable, czyli model może powiedzieć „nie wiem”.** W schemacie JSON `origin` ma typ
`["string", "null"]`. Gdy użytkownik nie poda miasta wyjazdu, model zwraca `null` zamiast
zgadywać, a nasz kod odpowiada czytelnym 422 („Nie rozpoznano miejsca wyjazdu”).

**Jedne reguły dla AI i formularza.** Dane z formularza przechodzą przez tę samą funkcję
`build_travel_intent()` co odpowiedź modelu: data nie w przeszłości, skąd ≠ dokąd,
domyślny priorytet.

**Ochrona przed prompt injection przez ograniczenia, a nie prośby.** Model nie zna klucza API,
może zwrócić tylko 4 pola zgodne ze schematem, odpowiedź jest walidowana, a zapytanie ma limit
300 znaków. Najgorszy możliwy efekt to dziwna nazwa miasta, której Transitous nie znajdzie.

**Łagodna degradacja.** Gdy Transitous nie odpowiada przy szukaniu połączeń, pokazujemy szacunek
lotu z ostrzeżeniem. Gdy AI padnie w trakcie (limit, timeout), frontend przełącza się na formularz.
422 oznacza „popraw zapytanie”, a 503 „problem po naszej stronie lub u dostawcy”.

**CO₂ ze sprawdzonego źródła.** Współczynniki pochodzą z oficjalnego arkusza
[UK GHG Conversion Factors 2025](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025),
z identyfikatorem wiersza w komentarzu. Współczynnik lotniczy uwzględnia radiative forcing
i zawiera już 8% dopłaty do dystansu, więc nie doliczamy jej drugi raz. Dystans pociągu liczymy
po przystankach pośrednich, nie w linii prostej. Zmiana trybu etapu przelicza CO₂ po stronie backendu.

**Ranking z rozstrzyganiem remisów.** Klucz sortowania to krotka, np. dla „ekologicznie”
`(co2, czas, koszt)`. Przy równej emisji wygrywa szybsza opcja, więc kolejność nie zależy
od przypadku.

**Uczciwe API Transitous.** Każde zapytanie ma nagłówek `User-Agent` z nazwą, wersją i kontaktem.
Odpowiedzi są cache'owane w SQLite (geokodowanie przez 30 dni, rozkłady przez 1 godzinę), ale tylko
udane: chwilowy błąd 503 nie zablokuje wyszukiwania na godzinę. Atrybucja źródeł jest stale widoczna w UI.

**Testy bez internetu i bez klucza.** Klienci HTTP są wstrzykiwani: `httpx.MockTransport` udaje
Transitous i Groq (testujemy prawdziwy SDK `openai`, tylko z podmienionym transportem), a zegar
w cache'u i planerze da się zamrozić. Testy strażnicze pilnują, by każdy tryb transportu miał
współczynnik CO₂ i stawkę kosztu, a ręcznie pisany schemat JSON był zgodny z modelem Pydantic.

**Daty i strefy czasowe.** Backend przyjmuje tylko czasy ze strefą (`AwareDatetime`) i zwraca UTC.
Frontend wyświetla je w strefie przeglądarki i omija klasyczne pułapki: `toISOString()` daje datę
w UTC, `new Date("2026-11-19")` to północ UTC, a `datetime-local` nie zna stref.

## Uruchomienie

Wymagania: [conda](https://docs.conda.io/) (Miniconda lub Anaconda) i git.

```bash
git clone <adres-repozytorium>
cd AI-trip-planner

# 1. Środowisko (Python 3.12 + Node.js 22)
conda env create -f environment.yml
conda activate development

# 2. Konfiguracja
cp .env.example .env
# W .env uzupełnij:
#   APP_CONTACT=  e-mail lub URL repozytorium (wymagane przez Transitous)
#   GROQ_API_KEY= klucz z https://console.groq.com/keys (opcjonalny, bez niego działa formularz)

# 3. Backend (terminal 1) → http://localhost:8000/docs
cd backend
fastapi dev app/main.py

# 4. Frontend (terminal 2) → http://localhost:5173
cd frontend
npm install
npm run dev
```

> Jeśli masz też Node.js z Homebrew, sprawdź `which node`. Projekt wymaga Node ≥ 22,
> a conda dostarcza wersję 22.

### Testy i jakość kodu

```bash
cd backend && ruff check . && ruff format --check . && pytest
cd frontend && npm run lint && npm test && npm run build
```

### Ręczne testy na prawdziwych API

Te skrypty wysyłają kilka prawdziwych zapytań, więc wymagają `.env`:

```bash
cd backend
python -m scripts.intent_smoke        # parser AI (Groq)
python -m scripts.transitous_smoke    # połączenia (Transitous)
```

## API

Interaktywna dokumentacja (Swagger UI) jest pod `http://localhost:8000/docs`.

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/health` | status i dostępność AI |
| POST | `/api/plan` | `{"query": "..."}` albo `{"origin", "destination", "travel_date", "priority"}` |
| GET / POST | `/api/trips` | lista / zapis planu (201) |
| GET / PATCH / DELETE | `/api/trips/{id}` | szczegóły / zmiana / usunięcie (204) |
| PATCH / DELETE | `/api/trips/{id}/legs/{leg_id}` | edycja / usunięcie etapu |

Kody odpowiedzi: 200, 201, 204, 404 (brak zasobu), 422 (błędne dane lub nierozpoznane
zapytanie), 503 (AI lub Transitous niedostępne).

## Struktura

```
backend/
  app/
    main.py              # create_app(), lifespan, CORS
    config.py            # ustawienia z .env (pydantic-settings, SecretStr)
    models.py            # Trip, Leg + schematy API
    routers/             # tylko HTTP: health, trips, plan
    services/
      intent_parser.py   # Groq: zdanie → TravelIntent
      transitous.py      # klient MOTIS 2: geocode, plan
      cache.py           # cache odpowiedzi w SQLite z TTL
      emissions.py       # haversine, współczynniki CO₂ (czyste funkcje)
      planner.py         # szacunek lotu, koszt, ranking, rekomendacja
      trips.py           # CRUD
  scripts/               # ręczne testy na prawdziwych API
  tests/
frontend/
  src/
    api/                 # typy i typowany klient API
    components/          # SearchForm, PlanResults, SavedTrips, Footer
    format.ts            # formatowanie dat, czasu, odmiana
```

## Ograniczenia (świadome)

- **Koszt to szacunek.** Transitous nie podaje cen biletów, więc koszt liczymy z orientacyjnych
  stawek za kilometr (`FARE_ASSUMPTIONS` w `planner.py`). Jest oznaczony w UI.
- **Lot to porównanie „miasto → miasto”.** Dystans liczymy w linii prostej, a czas ze średnią
  prędkością. Nie sprawdzamy lotnisk ani rozkładów lotów. Lot proponujemy od 300 km.
- **Współczynniki CO₂** to średnie dla Wielkiej Brytanii. Realna emisja pociągu zależy od miksu
  energii w danym kraju.
- **Godzina wyszukiwania**: połączenia szukamy od 05:00 UTC w dniu podróży.
- **Transitous** pozwala tylko na użycie niekomercyjne w projektach open source
  ([zasady API](https://transitous.org/api/)).

## Jak powstał ten projekt (użycie AI)

Kod powstawał w parze z asystentem AI (Claude Code). Autor prowadził repozytorium, podejmował
decyzje i weryfikował zmiany, a asystent generował kod i tłumaczył go.

- **[`CLAUDE.md`](CLAUDE.md)**: zasady współpracy, architektura i plan pracy w 12 krokach
  (jeden krok = jeden branch, małe commity w stylu Conventional Commits, `git merge --no-ff`).
- **[`.claude/settings.json`](.claude/settings.json)**: techniczna blokada, przez którą asystent
  **nie może** wykonać `git add/commit/push/merge/switch/reset/...` ani `rm -rf`. Każdy commit
  i merge zrobił człowiek, po przejrzeniu zmian.
- Przed każdym commitem musiały przechodzić `ruff check`, `ruff format` i `pytest`
  (a dla frontendu `lint`, `test` i `build`).

## Licencja

[MIT](LICENSE). Dane: rozkłady jazdy z [Transitous i jego źródeł](https://transitous.org/sources/),
geokodowanie © [współtwórcy OpenStreetMap](https://www.openstreetmap.org/copyright).
