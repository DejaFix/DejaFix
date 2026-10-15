"""#5 GET /api/dashboard/summary

스텁이다 — libs/zabbix_ro(T30) 가 생기면 T32 에서 Zabbix(호스트 가용성) + shared.db 집계로 교체한다.
"""

from fastapi import APIRouter, Depends

from dejafix_backend.deps import require_role
from dejafix_backend.stubs import load_example

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(_: dict = Depends(require_role("viewer"))):
    # TODO(T32): KPI 4종을 실제로 계산 (모두 Measured). Zabbix 끊기면 호스트 KPI 만 unknown(TOOL_ERROR)
    return load_example("summary_200")
