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
import sys
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


def text_matching(pattern: str, flags: int = re.IGNORECASE):
    """파일 **전체**를 한 문자열로 보고 찾는다 — 여러 줄에 걸친 SQL·호출도 잡는다."""
    regex = re.compile(pattern, flags | re.DOTALL)
    found = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            snippet = " ".join(match.group(0).split())[:100]
            found.append(f"{path.relative_to(SRC.parent)}:{line}: {snippet}")
    return found


def test_the_scan_covers_the_backend_source():
    """검사가 빈 목록을 훑고 '통과'하는 일이 없도록."""
    names = {p.name for p in SOURCES}
    assert {"main.py", "chat.py", "incidents.py", "worker.py"} <= names


# ---------------------------------------------------------------- 답변 기준 일원화


# LLM 을 직접 부르는 흔적: 라이브러리·엔드포인트 이름, LLM 설정 키, LLM_* 환경 변수를 **읽는** 코드.
# `llm_usage_today`(API 5번 응답 키)나 `"LLM_TIMEOUT"`(Agent 가 보낸 오류 코드를 전달·비교) 같은 정상 이름은 걸리지 않는다.
LLM_CLIENT_PATTERN = (
    r"openai|anthropic|litellm|langchain|ollama|openrouter|chat/completions"
    r"|llm_base_url|llm_api_key|llm_model"
    r"|(environ\[|environ\.get\(|getenv\()\s*[\"']LLM_"
)


def test_backend_has_no_llm_client():
    """LLM 호출은 Agent 한 곳에서만 한다 (NFR-MAINT-010)."""
    hits = lines_matching(LLM_CLIENT_PATTERN)
    assert hits == [], "backend 에 LLM 호출 흔적이 있다:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "line",
    [
        "from openai import OpenAI",
        "url = settings.llm_base_url",
        "key = settings.LLM_API_KEY  # llm_api_key",
        'model = os.environ["LLM_MODEL"]',
        "token = os.getenv('LLM_TOKEN')",
        'httpx.post("https://api.example/v1/chat/completions")',
    ],
)
def test_llm_pattern_catches_direct_use(line):
    assert re.search(LLM_CLIENT_PATTERN, line, re.IGNORECASE), line


@pytest.mark.parametrize(
    "line",
    [
        '"llm_usage_today": None,  # API 5번 계약의 응답 키(필수 단계는 null)',
        'if event["code"] == "LLM_TIMEOUT":',
        'ERRORS = {"LLM_NOT_CONFIGURED", "LLM_ERROR"}  # Agent 가 보내는 오류 코드',
        "llm_usage = None",
    ],
)
def test_llm_pattern_does_not_flag_contract_names_and_error_codes(line):
    """정상 이름을 막으면 Backend 가 계약대로 키를 넣는 순간 안전 테스트가 실패한다(오탐)."""
    assert not re.search(LLM_CLIENT_PATTERN, line, re.IGNORECASE), line


# Backend 가 HTTP 로 부르는 곳은 Agent(채팅 중계)와 Agent·MCP 상태 확인, 총괄(orchestrator) 읽기 중계(GET 두 개,
# contracts/api.md 6장)뿐이다. 새 호출처가 생기면 여기서 걸린다.
HTTP_CLIENT_IMPORT = r"^\s*(import|from)\s+(httpx|requests|aiohttp|urllib3|urllib\.request|http\.client)\b"
HTTP_ALLOWED = {"chat.py", "health.py", "orchestrator.py"}


def http_client_users(paths):
    return {
        p.name
        for p in paths
        if re.search(HTTP_CLIENT_IMPORT, p.read_text(encoding="utf-8"), re.M)
    }


def test_http_client_is_used_only_where_the_backend_talks_to_agent_or_mcp():
    users = http_client_users(SOURCES)
    assert users <= HTTP_ALLOWED, (
        f"HTTP 클라이언트를 쓰는 새 파일: {sorted(users - HTTP_ALLOWED)} — Agent·MCP 가 아닌 곳을 "
        "부르는 것이면 LLM·Zabbix 직접 호출이 아닌지 먼저 확인하고 이 목록을 고친다"
    )


@pytest.mark.parametrize(
    "source",
    [
        "import requests",
        "import aiohttp\n",
        "from urllib.request import urlopen",
        "import http.client",
        "    import httpx",
        "from httpx import AsyncClient",
        "import urllib3",
    ],
)
def test_http_client_detection_covers_every_common_library(tmp_path, source):
    sneaky = tmp_path / "sneaky.py"
    sneaky.write_text(source, encoding="utf-8")
    assert http_client_users([sneaky]) == {"sneaky.py"}


def test_http_client_detection_ignores_unrelated_text(tmp_path):
    quiet = tmp_path / "quiet.py"
    quiet.write_text("# requests 를 쓰지 않는다\nimport smtplib\n", encoding="utf-8")
    assert http_client_users([quiet]) == set()


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


ZABBIX_ADDRESS = r"(?<!mcp_)zabbix_url|zabbix_api_token"
ZABBIX_RO_IMPORT = r"^\s*(import zabbix_ro|from zabbix_ro)\b"


def zabbix_address_violations(paths):
    """ZABBIX_URL·토큰을 쓰는 파일(설정 config.py 제외)은 **zabbix_ro 를 실제로 import** 해야 한다.

    주석이나 문자열에 'zabbix_ro' 가 적혀 있는 것만으로는 통과하지 않는다.
    """
    bad = []
    for path in paths:
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(ZABBIX_ADDRESS, text, re.IGNORECASE) and not re.search(
            ZABBIX_RO_IMPORT, text, re.MULTILINE
        ):
            bad.append(path.name)
    return bad


def test_zabbix_address_and_token_only_go_into_zabbix_ro():
    assert zabbix_address_violations(SOURCES) == []


def test_zabbix_address_check_is_not_vacuous(tmp_path):
    """위 검사가 실제로 위반을 잡고, 올바른 사용은 통과시키는지 (지금 소스에는 해당 파일이 없어도 검사가 살아 있게)."""
    comment_only = tmp_path / "comment_only.py"
    comment_only.write_text(
        "# zabbix_ro 를 쓸 예정\nURL = settings.zabbix_url\n", encoding="utf-8"
    )
    direct = tmp_path / "direct.py"
    direct.write_text(
        "import httpx\nhttpx.get(settings.zabbix_url, headers={'t': settings.zabbix_api_token})\n",
        encoding="utf-8",
    )
    proper = tmp_path / "proper.py"
    proper.write_text(
        "import zabbix_ro\nclient = zabbix_ro.from_env({'ZABBIX_URL': settings.zabbix_url})\n",
        encoding="utf-8",
    )
    from_import = tmp_path / "from_import.py"
    from_import.write_text(
        "from zabbix_ro import from_env\nfrom_env({'ZABBIX_URL': settings.zabbix_url})\n",
        encoding="utf-8",
    )
    mcp_only = tmp_path / "mcp_only.py"
    mcp_only.write_text("URL = settings.mcp_zabbix_url\n", encoding="utf-8")
    assert zabbix_address_violations(
        [comment_only, direct, proper, from_import, mcp_only]
    ) == ["comment_only.py", "direct.py"]


def test_backend_never_writes_to_shared_tables():
    """shared.db 는 Agent·Scheduler 만 쓴다. Backend 는 ATTACH 읽기 전용 + backend.db 에만 쓴다."""
    shared_tables = (
        "incidents|agent_runs|tool_calls|analysis_reports|change_plans|plan_steps|"
        "conversations|messages|scheduler_jobs|plan_reviews"
    )
    write = r"(insert\s+(or\s+\w+\s+)?into|update|delete\s+from|replace\s+into|drop\s+table|alter\s+table)"
    # 줄바꿈으로 나뉜 SQL("INSERT INTO\n    shared.incidents")도 잡도록 파일 전체를 본다
    hits = text_matching(rf"{write}\s+(shared\.)?({shared_tables})\b")
    assert hits == [], "shared 테이블에 쓰는 SQL:\n" + "\n".join(hits)


def test_the_multiline_scan_catches_a_split_sql_statement(tmp_path, monkeypatch):
    """위 검사가 여러 줄 SQL 을 실제로 잡는지(빈틈 확인용)."""
    bad = tmp_path / "bad.py"
    bad.write_text("SQL = '''\nINSERT INTO\n    shared.incidents (id)\nVALUES (1)'''\n")
    monkeypatch.setattr(sys.modules[__name__], "SOURCES", [bad])
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)
    assert text_matching(r"insert\s+into\s+shared\.incidents")
    assert not lines_matching(
        r"insert\s+into\s+shared\.incidents"
    )  # 줄 단위로는 못 본다


# ---------------------------------------------------------------- 실행 경로 없음


FORBIDDEN_KEYS = {"execute", "executed", "run", "apply", "applied", "command_run"}
# 변형(can_execute·run_command·auto_apply …)도 막는다. run_id·run_status 처럼 run 이 이름 일부인 정상 키는 허용한다.
FORBIDDEN_KEY_PATTERN = re.compile(
    r"(^|_)(execute|executed|executes|exec|apply|applied)(_|$)"
    r"|(^|_)run_(command|cmd|now|action|plan|step)"
    r"|(can|do|allow|auto)_?(run|execute|exec|apply)"
    r"|command_run",
    re.IGNORECASE,
)


def is_forbidden_key(key: str) -> bool:
    return key.lower() in FORBIDDEN_KEYS or bool(FORBIDDEN_KEY_PATTERN.search(key))


@pytest.mark.parametrize(
    "key,forbidden",
    [
        ("execute", True),
        ("run", True),
        ("can_execute", True),
        ("canExecute", True),
        ("run_command", True),
        ("auto_apply", True),
        ("applied", True),
        ("exec", True),
        ("run_id", False),  # 정상: 근거가 저장된 run 의 ID
        ("run_status", False),
        ("report_id", False),
        ("duration_ms", False),
        ("tier", False),
        ("max_tier", False),
        ("precheck", False),
    ],
)
def test_forbidden_key_rule(key, forbidden):
    assert is_forbidden_key(key) is forbidden


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
        bad = [p for p, key in walk_keys(body) if is_forbidden_key(key)]
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
