"""ZABBIX_MOCK=true 일 때 쓰는 고정 응답 (Zabbix 7.0.31 실서버 응답 기준).

fixtures/ 는 `docs/zabbix/verification/api-probe-2026-10-14/` 의 실제 응답(result 부분)을 복사한 것이다.
trigger.get 의 hosts 에는 host.get 의 `name` 을 보강했다(Scheduler 가 selectHosts 로 name 을 요청).
fixture 가 없는 허용 메서드는 빈 목록을 돌려준다.
"""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent / "fixtures"

# 요청 파라미터의 id 목록 → 레코드의 키 (값이 있을 때만 거른다)
_ID_FILTERS = {
    "eventids": "eventid",
    "triggerids": "triggerid",
    "hostids": "hostid",
    "itemids": "itemid",
    "objectids": "objectid",
}


@cache
def _load(name: str) -> Any:
    path = _DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def mock_result(method: str, params: dict[str, Any]) -> Any:
    """허용 메서드에 대한 고정 응답. 호출자가 수정해도 원본이 바뀌지 않게 복사해서 준다."""
    if method == "history.get":
        data = _load(f"history.get.type{params.get('history', 3)}")
    else:
        data = _load(method)
    if data is None:
        return []
    data = copy.deepcopy(data)
    if not isinstance(data, list):
        return data  # apiinfo.version 은 문자열

    for param, key in _ID_FILTERS.items():
        wanted = _as_list(params.get(param))
        if wanted:
            data = [r for r in data if key not in r or str(r[key]) in wanted]
    limit = params.get("limit")
    if isinstance(limit, int) and limit >= 0:
        data = data[:limit]
    return data
