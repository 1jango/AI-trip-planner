"""Testy parsera intencji. Prawdziwy SDK `openai`, ale z podmienionym transportem httpx —
sprawdzamy, co faktycznie wysyłamy do Groq, bez internetu i bez klucza."""

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from app.models import Priority
from app.services.intent_parser import (
    CALENDAR_DAYS_AHEAD,
    DEFAULT_PRIORITY,
    INTENT_JSON_SCHEMA,
    MAX_QUERY_LENGTH,
    AiUnavailableError,
    IntentNotUnderstoodError,
    IntentParser,
    LlmIntentResponse,
    build_system_prompt,
    build_travel_intent,
    create_groq_client,
    create_intent_parser,
)
from tests.conftest import make_settings

TODAY = date(2026, 11, 13)  # piątek
NEXT_THURSDAY = date(2026, 11, 19)
MODEL = "openai/gpt-oss-120b"

Handler = Callable[[httpx.Request], httpx.Response]


def chat_completion(content: str | None, finish_reason: str = "stop") -> dict[str, Any]:
    """Minimalna odpowiedź w formacie OpenAI Chat Completions."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


def intent_json(
    origin: str | None = "Gdańsk",
    destination: str | None = "'s-Hertogenbosch",
    travel_date: str | None = "2026-11-19",
    priority: str | None = "cheap",
) -> str:
    return json.dumps(
        {
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date,
            "priority": priority,
        }
    )


class FakeGroq:
    """Atrapa serwera Groq: zapamiętuje zapytania i zwraca to, co ustawimy."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def last_body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)


def make_parser(handler: Handler) -> tuple[IntentParser, FakeGroq]:
    server = FakeGroq(handler)
    http_client = httpx.Client(transport=httpx.MockTransport(server))
    client = create_groq_client("test-key", http_client=http_client)
    # Bez ponowień: test błędu 500 nie czeka na backoff i widzi dokładnie 1 zapytanie.
    return IntentParser(client.with_options(max_retries=0), MODEL), server


def respond_with(content: str | None, finish_reason: str = "stop") -> Handler:
    return lambda request: httpx.Response(200, json=chat_completion(content, finish_reason))


# --- Szczęśliwa ścieżka i to, co wysyłamy ---


def test_parses_sentence_into_travel_intent() -> None:
    parser, _ = make_parser(respond_with(intent_json()))

    intent = parser.parse("Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej", TODAY)

    assert intent.origin == "Gdańsk"
    assert intent.destination == "'s-Hertogenbosch"
    assert intent.travel_date == NEXT_THURSDAY
    assert intent.priority == Priority.CHEAP


def test_request_uses_strict_json_schema_and_deterministic_settings() -> None:
    parser, server = make_parser(respond_with(intent_json()))

    parser.parse("Gdańsk do Berlina jutro", TODAY)

    body = server.last_body()
    assert body["model"] == MODEL
    assert body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == INTENT_JSON_SCHEMA


def test_request_sends_api_key_to_groq_endpoint() -> None:
    parser, server = make_parser(respond_with(intent_json()))

    parser.parse("Gdańsk do Berlina jutro", TODAY)

    request = server.requests[-1]
    assert request.headers["Authorization"] == "Bearer test-key"
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"


def test_user_text_goes_only_into_user_message_with_normalized_whitespace() -> None:
    parser, server = make_parser(respond_with(intent_json()))

    parser.parse("  Gdańsk \n\n do   Berlina\tjutro  ", TODAY)

    system_message, user_message = server.last_body()["messages"]
    assert system_message["role"] == "system"
    assert "Berlina" not in system_message["content"]
    assert user_message == {"role": "user", "content": "Gdańsk do Berlina jutro"}


# --- Walidacja wejścia (bez wywołania AI) ---


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_is_rejected_without_calling_ai(query: str) -> None:
    parser, server = make_parser(respond_with(intent_json()))

    with pytest.raises(IntentNotUnderstoodError, match="puste"):
        parser.parse(query, TODAY)
    assert server.requests == []


def test_too_long_query_is_rejected_without_calling_ai() -> None:
    parser, server = make_parser(respond_with(intent_json()))

    with pytest.raises(IntentNotUnderstoodError, match="za długie"):
        parser.parse("a" * (MAX_QUERY_LENGTH + 1), TODAY)
    assert server.requests == []


def test_query_at_max_length_is_accepted() -> None:
    parser, _ = make_parser(respond_with(intent_json()))

    parser.parse("a" * MAX_QUERY_LENGTH, TODAY)  # granica włącznie — brak wyjątku


# --- Błędy AI → AiUnavailableError (fallback na formularz) ---


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def status(code: int) -> Handler:
    return lambda request: httpx.Response(code, json={"error": {"message": "boom"}})


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (raise_timeout, "na czas"),
        (raise_connect_error, "połączenia"),
        (status(429), "limit"),
        (status(401), "klucz"),
        (status(500), "HTTP 500"),
        (respond_with(None), "niepełną"),
        (respond_with(intent_json(), finish_reason="length"), "niepełną"),
        (respond_with("to nie jest JSON"), "formacie"),
        (respond_with('{"origin": "Gdańsk"}'), "formacie"),
        (respond_with(intent_json(priority="luxury")), "formacie"),
        (lambda request: httpx.Response(200, json={**chat_completion(""), "choices": []}), "pustą"),
    ],
    ids=[
        "timeout",
        "connection-error",
        "rate-limit",
        "bad-api-key",
        "server-error",
        "null-content",
        "truncated",
        "not-json",
        "missing-fields",
        "unknown-priority",
        "no-choices",
    ],
)
def test_ai_problems_raise_ai_unavailable(handler: Handler, message: str) -> None:
    parser, _ = make_parser(handler)

    with pytest.raises(AiUnavailableError, match=message):
        parser.parse("Gdańsk do Berlina jutro", TODAY)


# --- Reguły biznesowe: czysta funkcja build_travel_intent ---


def llm_response(**overrides: Any) -> LlmIntentResponse:
    values: dict[str, Any] = {
        "origin": "Gdańsk",
        "destination": "Berlin",
        "travel_date": NEXT_THURSDAY,
        "priority": Priority.GREEN,
    }
    values.update(overrides)
    return LlmIntentResponse(**values)


def test_missing_date_defaults_to_today() -> None:
    assert build_travel_intent(llm_response(travel_date=None), TODAY).travel_date == TODAY


def test_missing_priority_uses_default() -> None:
    assert build_travel_intent(llm_response(priority=None), TODAY).priority == DEFAULT_PRIORITY


def test_place_names_are_stripped() -> None:
    intent = build_travel_intent(llm_response(origin="  Gdańsk ", destination=" Berlin"), TODAY)

    assert (intent.origin, intent.destination) == ("Gdańsk", "Berlin")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"origin": None}, "wyjazdu"),
        ({"origin": "   "}, "wyjazdu"),
        ({"destination": None}, "docelowego"),
        ({"destination": "gdańsk"}, "takie same"),
        ({"travel_date": TODAY - timedelta(days=1)}, "przeszłości"),
        ({"travel_date": TODAY + timedelta(days=366)}, "rok"),
        ({"origin": "x" * 201}, "zbyt długa"),
    ],
    ids=[
        "no-origin",
        "blank-origin",
        "no-destination",
        "same-place-case-insensitive",
        "past-date",
        "too-far-ahead",
        "place-too-long",
    ],
)
def test_invalid_intent_is_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(IntentNotUnderstoodError, match=message):
        build_travel_intent(llm_response(**overrides), TODAY)


@pytest.mark.parametrize("days_ahead", [0, 365], ids=["today", "exactly-one-year"])
def test_date_boundaries_are_inclusive(days_ahead: int) -> None:
    travel_date = TODAY + timedelta(days=days_ahead)

    assert build_travel_intent(llm_response(travel_date=travel_date), TODAY).travel_date == (
        travel_date
    )


# --- Prompt i schemat ---


def test_system_prompt_contains_calendar_with_weekdays() -> None:
    prompt = build_system_prompt(TODAY)

    assert "- 2026-11-13 Friday (today)" in prompt
    assert "- 2026-11-19 Thursday" in prompt
    last_day = TODAY + timedelta(days=CALENDAR_DAYS_AHEAD - 1)
    assert last_day.isoformat() in prompt
    assert (last_day + timedelta(days=1)).isoformat() not in prompt


def test_json_schema_matches_pydantic_model() -> None:
    """Strażnik: schemat jest pisany ręcznie — po dodaniu pola do modelu ten test
    przypomni o aktualizacji schematu (i odwrotnie)."""
    assert set(INTENT_JSON_SCHEMA["properties"]) == set(LlmIntentResponse.model_fields)
    assert set(INTENT_JSON_SCHEMA["required"]) == set(LlmIntentResponse.model_fields)
    priority_enum = INTENT_JSON_SCHEMA["properties"]["priority"]["enum"]
    assert set(priority_enum) == {*(priority.value for priority in Priority), None}


# --- Fabryka: brak klucza = brak AI ---


@pytest.mark.parametrize("api_key", [None, "", "   "], ids=["none", "empty", "blank"])
def test_no_parser_without_api_key(api_key: str | None) -> None:
    assert create_intent_parser(make_settings(groq_api_key=api_key)) is None


def test_parser_is_created_with_api_key() -> None:
    assert isinstance(create_intent_parser(make_settings(groq_api_key="key")), IntentParser)
