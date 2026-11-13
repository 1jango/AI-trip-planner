# CLAUDE.md — AI Trip Planner

Instrukcje dla Claude Code w tym repozytorium. Projekt to zadanie rekrutacyjne na staż
w Xelerit (Gdańsk), termin: **15.11.2026, 23:59**. Autor jest juniorem — Claude generuje
kod i wyjaśnia go, autor prowadzi repozytorium.

## 1. Zasady pracy z Git (NAJWAŻNIEJSZE)

- Claude **NIGDY** nie wykonuje operacji zapisu w Git: `git add`, `commit`, `push`, `merge`,
  `checkout`, `switch`, `branch`, `reset`, `rebase`, `stash`, `restore`, `rm`, ani `gh pr`.
- Dozwolone są tylko komendy odczytu: `git status`, `git diff`, `git log`.
- Blokada jest też wymuszona technicznie w `.claude/settings.json` (`permissions.deny`).
- Na początku każdego kroku Claude podaje nazwę brancha i komendę, np.
  `git switch -c feature/trips-crud`, i czeka na potwierdzenie.
- Gdy kod jest gotowy, Claude podaje: listę plików, wiadomość commita
  (Conventional Commits, po angielsku: `feat:`, `fix:`, `chore:`, `test:`, `docs:`,
  `refactor:`) i gotowe komendy do skopiowania. Duże zmiany = kilka małych commitów.
- Na koniec kroku Claude podaje komendy push i merge do `main` (`git merge --no-ff`),
  ale ich nie wykonuje.
- Przed propozycją commita muszą przechodzić: `ruff check`, `ruff format`, `pytest`.
- Po każdym kroku Claude zatrzymuje się i czeka na „dalej”.

## 2. Bezpieczeństwo

- Zakazane zawsze: `rm -rf`, commitowanie `.env`, sekretów, `*.db`, `node_modules`.
- Sekrety tylko w `.env` (ignorowany). Szablon zmiennych: `.env.example` (bez wartości).

## 3. Sposób wyjaśniania

- Pokazuj zmiany i wyjaśniaj: co robi kod, dlaczego tak, jakie są alternatywy
  i typowe błędy juniorów w danym miejscu.
- Czytelność ponad spryt, opisowe nazwy, obsługa błędów, testy do nowego kodu.

## 4. Projekt

Webowa aplikacja full-stack (MVP). Użytkownik wpisuje podróż zdaniem, np.
„Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej”, a aplikacja zwraca plan
z etapami (pociąg/autobus/lot), czasem i CO₂. Plany można zapisywać, przeglądać,
edytować i usuwać (CRUD).

### Architektura — AI nie wymyśla danych

1. LLM **tylko** parsuje zdanie do JSON-a (`origin`, `destination`, `travel_date`,
   `priority: cheap|fast|green`), Pydantic go waliduje.
2. Prawdziwe połączenia z Transitous API (https://api.transitous.org, MOTIS 2):
   nagłówek `User-Agent` z nazwą aplikacji, wersją i kontaktem; cache w SQLite;
   mało zapytań; link do https://transitous.org/sources w UI.
3. Loty: dystans haversine, czas i CO₂ jako szacunek — oznaczone w UI.
4. CO₂, sortowanie i rekomendację liczy deterministyczny, przetestowany kod.
5. Opcjonalnie LLM pisze jednozdaniowe uzasadnienie.
6. Fallback: bez klucza API działa zwykły formularz, UI pokazuje „AI niedostępne”.

## 5. Stack

- **conda**, środowisko `development`, zależności w `environment.yml` (conda-forge).
  Nowe biblioteki: dopisz do `environment.yml` i podaj komendę
  `conda env update -n development -f environment.yml` (bez `--prune`).
- **Backend** (`backend/`): FastAPI, SQLModel + SQLite, httpx, pydantic-settings (`.env`),
  pytest, ruff.
- **AI**: Groq (SDK `openai`), model `openai/gpt-oss-120b`, structured outputs;
  klient wstrzykiwany — testy działają bez internetu i bez klucza.
- **Frontend** (`frontend/`): React + TypeScript + Vite, bez `any`.
- **CORS**: tylko `http://localhost:5173`.

## 6. Struktura backendu

```
backend/
  app/
    main.py
    config.py
    models.py            # Trip, Leg
    routers/             # tylko warstwa HTTP
    services/
      intent_parser.py
      transitous.py
      emissions.py       # czyste funkcje
  tests/
```

- `Trip` (id, name, origin, destination, travel_date, priority, created_at) 1→N
- `Leg` (id, trip_id, mode, from_place, to_place, departure, arrival, distance_km,
  co2_kg, source: `"transitous"|"estimate"`)

### REST

| Metoda | Ścieżka                              |
|--------|--------------------------------------|
| POST   | `/api/plan`                          |
| GET    | `/api/trips`                         |
| POST   | `/api/trips`                         |
| GET    | `/api/trips/{id}`                    |
| PATCH  | `/api/trips/{id}`                    |
| DELETE | `/api/trips/{id}`                    |
| PATCH  | `/api/trips/{id}/legs/{leg_id}`      |
| DELETE | `/api/trips/{id}/legs/{leg_id}`      |

Kody odpowiedzi: 201, 204, 404, 422.

## 7. Plan (jeden krok = jeden branch)

0. `chore/project-setup` — CLAUDE.md, .env.example, konfiguracja repo.
1. `feature/backend-skeleton` — app, config, CORS, `GET /api/health` + test.
2. `feature/trips-crud` — modele, SQLite, CRUD + testy (baza in-memory).
3. `feature/emissions` — haversine, współczynniki CO₂ ze źródłem w komentarzu + testy.
4. `feature/transitous-client` — geokodowanie, połączenia, User-Agent, cache, timeouty
   + testy z mockiem httpx.
5. `feature/ai-intent-parser` — parser Groq z fallbackiem + testy z atrapą klienta.
6. `feature/plan-endpoint` — `POST /api/plan` + rekomendacja + testy.
7. `feature/frontend-skeleton` — Vite React-TS, typowany klient API, ESLint.
8. `feature/frontend-search-and-results` — zapytanie + formularz fallback, karty opcji,
   CO₂, stany ładowania i błędów.
9. `feature/frontend-saved-trips` — lista, szczegóły, edycja i usuwanie etapów.
10. `feature/ui-polish` — UX, atrybucja Transitous, oznaczenia „szacunek”.
11. `docs/readme` — README (opis, stack, ciekawsze rozwiązania, uruchomienie przez conda,
    użycie AI, CLAUDE.md i .claude/settings.json), miejsce na demo.gif.
