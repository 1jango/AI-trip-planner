"""POST /api/plan — tylko warstwa HTTP: zależności i zamiana wyjątków na kody odpowiedzi."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.models import PlanRequest, PlanResponse
from app.services import planner
from app.services.intent_parser import AiUnavailableError, IntentNotUnderstoodError
from app.services.planner import IntentSource, RouteProvider
from app.services.transitous import PlaceNotFoundError, TransitousUnavailableError

router = APIRouter(prefix="/api", tags=["plan"])


# Zależności jako osobne funkcje: testy podmieniają je przez app.dependency_overrides
# (atrapy klientów, zamrożony zegar), a kod endpointu zostaje bez zmian.


def get_intent_parser(request: Request) -> IntentSource | None:
    return request.app.state.intent_parser


def get_route_provider(request: Request) -> RouteProvider | None:
    return request.app.state.route_provider


def get_now() -> datetime:
    return datetime.now(UTC)


def service_unavailable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


@router.post("/plan", response_model=PlanResponse)
def create_plan(
    plan_request: PlanRequest,
    parser: IntentSource | None = Depends(get_intent_parser),
    provider: RouteProvider | None = Depends(get_route_provider),
    now: datetime = Depends(get_now),
) -> PlanResponse:
    if provider is None:
        raise service_unavailable(
            "Wyszukiwanie połączeń jest wyłączone: brak APP_CONTACT w konfiguracji serwera."
        )

    # 422 = problem z danymi od użytkownika (popraw zapytanie),
    # 503 = problem po naszej stronie lub u dostawcy (spróbuj później / użyj formularza).
    try:
        intent, parsed_by = planner.resolve_intent(plan_request, parser, now.date())
        return planner.build_plan(intent, parsed_by, provider, now)
    except IntentNotUnderstoodError as error:
        raise unprocessable(str(error)) from error
    except PlaceNotFoundError as error:
        raise unprocessable(str(error)) from error
    except AiUnavailableError as error:
        raise service_unavailable(str(error)) from error
    except TransitousUnavailableError as error:
        raise service_unavailable(str(error)) from error
