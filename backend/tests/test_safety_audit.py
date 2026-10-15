"""Backend 안전 점검 (T70·T73, N8) — `pytest -m safety_regression` 에 묶이는 검사들.

| 규칙 | 이 파일의 검사 | 기존 테스트 (같은 마커) |
|---|---|---|
| SAFE-02 Zabbix 읽기 전용 | backend 는 Zabbix 를 직접 부르지 않는다(libs/zabbix_ro 경유) | libs/zabbix_ro/tests |
| SAFE-04 실행 경로 없음 | 모든 GET 응답에 execute·run 계열 키가 없고 plan.mode 는 preview | test_incidents |
| SAFE-08 근거 | — | test_incidents (evidence_ids 가 evidence[] 에 존재) |
| SAFE-10 확인할 수 없는 값 | — | test_misc (KPI 는 Measured) |
| 단일 작성자 / ATTACH 읽기 전용 | backend 코드가 shared 테이블에 쓰는 SQL 이 없다 | test_db (readonly 오류) |
| NFR-MAINT-010 답변 기준 일원화 | backend 에 LLM 호출·티어 계산이 없다 | — |
| NFR-SEC 인증 | /api 아래 모든 경로는 토큰 없이 401 (로그인 제외) | test_auth |
"""

import re
from pathlib import Path

import pytest

import dejafix_backend

SRC = Path(dejafix_backend.__file__).resolve().parent
SOURCES = sorted(p for p in SRC.rglob("*.py"))

pytestmark = pytest.mark.safety_regression


def lines_matching(pattern: str, flags: int = re.IGNORECASE):
    regex = re.compile(pattern, flags)
    found = []
    for path in SOURCES:
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if regex.search(line):
                found.append(f"{path.relative_to(SRC.parent)}:{number}: {line.strip()}")
    return found


def test_the_scan_covers_the_backend_source():
    """검사가 빈 목록을 훑고 '통과'하는 일이 없도록."""
    names = {p.name for p in SOURCES}
    assert {"main.py", "chat.py", "incidents.py", "worker.py"} <= names


# ---------------------------------------------------------------- 답변 기준 일원화


def test_backend_has_no_llm_client():
    """LLM 호출은 Agent 한 곳에서만 한다 (NFR-MAINT-010)."""
    hits = lines_matching(
        r"openai|anthropic|litellm|langchain|ollama|openrouter|chat/completions"
    )
    assert hits == [], "backend 에 LLM 호출 흔적이 있다:\n" + "\n".join(hits)


def test_backend_does_not_compute_tiers():
    """티어(A/B/C)는 Agent 가 코드로 정하고 Backend 는 저장된 값을 읽어 전달만 한다 (SAFE-06·07)."""
    patterns = [
        r"tier\w*\W{1,6}[\"'][ABC][\"']",  # tier == "C", tier = "A" 같은 판정
        r"[\"'][ABC][\"']\W{1,6}tier",
        r"\b(max|min|sorted)\(.*tier",  # 티어 순위 계산
        r"actions\.yaml|packs/",  # 티어 규칙 파일을 직접 읽음
    ]
    hits = [h for pattern in patterns for h in lines_matching(pattern)]
    assert hits == [], "backend 가 티어를 계산하는 것처럼 보인다:\n" + "\n".join(hits)


# ---------------------------------------------------------------- Zabbix·DB 경계


def test_backend_reaches_zabbix_only_through_zabbix_ro():
    """JSON-RPC 를 직접 만들거나 쓰기 메서드 이름을 쓰는 코드가 없다 (SAFE-02)."""
    hits = lines_matching(
        r"api_jsonrpc|[\"']jsonrpc[\"']|user\.login|\.(update|create|delete|massupdate|execute)[\"']"
    )
    assert hits == [], "Zabbix 를 직접 다루는 코드:\n" + "\n".join(hits)


def test_backend_never_writes_to_shared_tables():
    """shared.db 는 Agent·Scheduler 만 쓴다. Backend 는 ATTACH 읽기 전용 + backend.db 에만 쓴다."""
    shared_tables = (
        "incidents|agent_runs|tool_calls|analysis_reports|change_plans|plan_steps|"
        "conversations|messages|scheduler_jobs|plan_reviews"
    )
    write = r"(insert\s+(or\s+\w+\s+)?into|update|delete\s+from|replace\s+into|drop\s+table|alter\s+table)"
    hits = lines_matching(rf"{write}\s+(shared\.)?({shared_tables})\b")
    assert hits == [], "shared 테이블에 쓰는 SQL:\n" + "\n".join(hits)


# ---------------------------------------------------------------- 실행 경로 없음


FORBIDDEN_KEYS = {"execute", "executed", "run", "apply", "applied", "command_run"}


def walk_keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}/{key}", key
            yield from walk_keys(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from walk_keys(item, f"{path}[{index}]")


def test_no_get_response_has_an_execute_key_and_plans_stay_preview(
    seeded_client, helpers
):
    headers = helpers.login(seeded_client, "oncall", helpers.oncall_password)
    listing = seeded_client.get("/api/incidents?limit=100", headers=headers).json()
    ids = [item["id"] for item in listing["data"]]
    assert ids, "시드 장애가 있어야 점검이 의미 있다"
    paths = [
        "/api/health",
        "/api/auth/me",
        "/api/dashboard/summary",
        "/api/problems",
        "/api/incidents?limit=100",
        *[f"/api/incidents/{i}" for i in ids],
    ]
    plans = 0
    for path in paths:
        response = seeded_client.get(path, headers=headers)
        assert response.status_code == 200, path
        body = response.json()
        bad = [p for p, key in walk_keys(body) if key.lower() in FORBIDDEN_KEYS]
        assert bad == [], f"{path} 에 실행 관련 키: {bad}"
        plan = body["data"].get("plan") if isinstance(body["data"], dict) else None
        if plan:
            plans += 1
            assert plan["mode"] == "preview", path
    assert plans >= 1, "계획이 있는 장애가 시드에 있어야 mode 점검이 의미 있다"


# ---------------------------------------------------------------- 인증


def test_every_api_route_requires_a_token_except_login(client):
    """새 경로를 추가하면서 인증을 빼먹으면 여기서 걸린다."""
    checked = []
    for path, operations in client.get("/openapi.json").json()["paths"].items():
        if not path.startswith("/api") or path == "/api/auth/login":
            continue
        for method in sorted(operations):
            url = re.sub(r"\{[^}]+\}", "1", path)
            response = client.request(method.upper(), url, json={"message": "x"})
            assert response.status_code == 401, (
                f"{method} {path} → {response.status_code}"
            )
            checked.append(f"{method} {path}")
    assert len(checked) >= 6, checked  # health·me·summary·problems·incidents(2)·chat
