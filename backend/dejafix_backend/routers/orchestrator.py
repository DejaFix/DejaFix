"""총괄(orchestrator) 읽기 중계 — `GET /api/orchestrator/incidents`·`/departments` (contracts/api.md 6장).

DejaFix 장애 대응에서 부서 에이전트들이 한 일을 총괄이 모아 둔다. 화면은 이 기록을 보기만 하고,
Backend 는 총괄의 읽기 API(`GET /api/incidents`·`/api/departments`)를 **그대로 중계**한다.
- 읽기 전용: 총괄로 보내는 요청은 GET 두 개뿐이다. 승인·장애 주입 같은 쓰기 경로는 중계하지 않는다.
- 분석·원인·티어·문장을 만들거나 바꾸지 않는다. 값은 총괄 응답 그대로이고, 단계 결과 본문(`output`)만 뺀다.
- 총괄이 없거나(`ORCHESTRATOR_URL` 비어 있음) 응답하지 않으면 503 `ORCHESTRATOR_UNAVAILABLE`
  (화면은 "확인할 수 없음"으로 그린다. 지어낸 값을 돌려주지 않는다).
"""

from typing import Any

import httpx
from fastapi import APIRouter, Depends

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

ORCHESTRATOR_TIMEOUT_SEC = 5.0


def get_orchestrator_transport() -> httpx.AsyncBaseTransport | None:
    """테스트에서 가짜 총괄로 바꿔 끼우는 자리. 운영은 None(실제 네트워크)."""
    return None


def _unavailable(message: str) -> ApiError:
    return ApiError(503, "ORCHESTRATOR_UNAVAILABLE", message)


async def _read(
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None,
    path: str,
) -> tuple[Any, dict[str, Any]]:
    """총괄에 GET 한 번. 성공하면 (data, meta), 아니면 503."""
    base = settings.orchestrator_url.rstrip("/")
    if not base:
        raise _unavailable(
            "총괄(orchestrator)이 연결되지 않았습니다 (ORCHESTRATOR_URL)"
        )
    try:
        async with httpx.AsyncClient(
            base_url=base,
            transport=transport,
            timeout=httpx.Timeout(ORCHESTRATOR_TIMEOUT_SEC, connect=2.0),
        ) as client:
            response = await client.get(path)
    except (httpx.HTTPError, OSError):
        raise _unavailable("총괄(orchestrator)에 연결할 수 없습니다") from None
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code != 200 or not isinstance(body, dict) or "data" not in body:
        raise _unavailable(
            f"총괄이 정상 응답하지 않았습니다 (HTTP {response.status_code})"
        )
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return body["data"], meta


def _without_step_output(incident: dict[str, Any]) -> dict[str, Any]:
    """단계 결과 본문(`output`)은 화면에 필요 없고 커질 수 있어 뺀다. 나머지는 그대로."""
    steps = [
        {k: v for k, v in step.items() if k != "output"}
        if isinstance(step, dict)
        else step
        for step in incident.get("steps", [])
    ]
    return {**incident, "steps": steps}


@router.get("/incidents")
async def orchestrator_incidents(
    _: dict[str, Any] = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
    transport: httpx.AsyncBaseTransport | None = Depends(get_orchestrator_transport),
):
    data, meta = await _read(settings, transport, "/api/incidents")
    if not isinstance(data, list):
        raise _unavailable("총괄 응답 형식이 맞지 않습니다")
    incidents = [_without_step_output(i) if isinstance(i, dict) else i for i in data]
    return ok(incidents, source="orchestrator", mock=bool(meta.get("mock")))


@router.get("/departments")
async def orchestrator_departments(
    _: dict[str, Any] = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
    transport: httpx.AsyncBaseTransport | None = Depends(get_orchestrator_transport),
):
    data, meta = await _read(settings, transport, "/api/departments")
    if not isinstance(data, list):
        raise _unavailable("총괄 응답 형식이 맞지 않습니다")
    return ok(
        data,
        source="orchestrator",
        mock=bool(meta.get("mock")),
        window_seconds=meta.get("window_seconds"),
        bucket_seconds=meta.get("bucket_seconds"),
    )
