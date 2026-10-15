"""#6 GET /api/problems

스텁이다 — libs/zabbix_ro(T30) 가 생기면 T32 에서 problem.get + trigger.get 실조회로 교체한다.
"""

from fastapi import APIRouter, Depends, Query

from dejafix_backend.deps import require_role
from dejafix_backend.stubs import load_example

router = APIRouter(tags=["problems"])


@router.get("/problems")
def problems(
    severity_min: int | None = Query(None, ge=0, le=5),
    hostid: str | None = None,
    _: dict = Depends(require_role("viewer")),
):
    # TODO(T32): Zabbix 실시간 조회 + incident_id 매칭, 실패 시 503 ZABBIX_UNAVAILABLE
    body = load_example("problems_200")
    items = body["data"]
    if severity_min is not None:
        items = [p for p in items if p["severity"]["level"] >= severity_min]
    if hostid is not None:
        items = [p for p in items if p["host"]["id"] == hostid]
    body["data"] = items
    return body
