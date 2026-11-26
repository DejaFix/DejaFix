"""화면에서 정한 Zabbix 연결 (연결 파일).

`ZABBIX_CONNECTION_FILE`(없으면 `BACKEND_DB_PATH`·`SHARED_DB_PATH` 옆 `zabbix_connection.json`) JSON 파일에 `{url, token, verify_tls}` 가 있으면 `from_env` 가
`ZABBIX_URL`·`ZABBIX_API_TOKEN`·`ZABBIX_VERIFY_TLS` 대신 이 값을 쓴다. 파일이 없거나 깨졌으면 환경 변수 그대로.
- 쓰는 쪽은 Backend 관리자 API(`PUT /api/settings/zabbix`)뿐이다. 파일은 0600, 임시 파일 → os.replace.
- 토큰은 파일에만 두고 로그·예외 문장에 넣지 않는다.
- `LiveClient` 는 파일이 바뀌면(수정 시각·크기) 다음 호출 때 클라이언트를 새로 만든다.
  Scheduler·mcp-zabbix 처럼 클라이언트를 오래 들고 있는 쪽이 재시작 없이 새 연결을 따른다.

회사별(결정 019, contracts/api.md 1장 "회사"·#29):
- `DEFAULT_COMPANY_ID` 가 있으면 회사 나누기가 켜진다. 파일은 `{"companies": {"<회사 ID>": {url, token,
  verify_tls, conn_id, updated_at, updated_by}}}` 모양이고, 018 모양(회사 없는 한 벌)은 기본 회사 것으로 읽는다.
- 어느 회사의 연결을 쓸지는 `ZABBIX_COMPANY`(없으면 기본 회사). 그 회사 연결이 없으면 다른 회사 연결로
  떨어지지 않는다. `.env` 연결(`ZABBIX_URL`)은 기본 회사만 쓴다.
- `conn_id`(`zc_` + 16진 12자)는 저장 때 **주소(url)가 바뀔 때만** 새로 만든다(토큰·verify_tls 만 바뀌면
  같은 Zabbix 라 그대로 — 장애가 닫혔다 다시 열려 재분석·메일이 겹치지 않게, 준하 님 #216 리뷰).
  018 모양 파일처럼 값이 없으면 주소 해시로 정한다(서비스마다 같은 값).
- `.env` 연결(기본 회사만)의 conn_id 는 `env:` + 주소 해시 12자(.env 주소가 바뀌어도 가른다).
- 연결 파일이 있는데 읽지 못하면(`connection_file_state` 가 "broken") 연결이 바뀐 것으로 보지 않는다
  (Scheduler 는 그 주기를 건너뛰고 장애를 닫지 않는다).
- `DEFAULT_COMPANY_ID` 가 없으면 018 그대로(회사 없음).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONNECTION_FILE_ENV = "ZABBIX_CONNECTION_FILE"
COMPANY_ENV = "ZABBIX_COMPANY"
DEFAULT_COMPANY_ENV = "DEFAULT_COMPANY_ID"
# .env 연결(기본 회사만)의 연결 구분값, 연결이 아예 없을 때의 값 (contracts/db-schema.sql 규칙 8)
ENV_CONN_ID = "env"
LEGACY_CONN_ID = "legacy"
# 회사 ID 형식 (contracts/api.md 1장 "회사": 영문 소문자·숫자·-, 64자 이하)
COMPANY_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")


# 연결 파일을 따로 정하지 않았으면 이 DB 파일과 같은 폴더의 zabbix_connection.json
# (compose 에서는 세 서비스가 같은 /data 볼륨을 쓴다. Backend 기본값과 같은 자리)
DEFAULT_NAME = "zabbix_connection.json"
_DB_ENVS = ("BACKEND_DB_PATH", "SHARED_DB_PATH")


def connection_path(env: Mapping[str, str] | None = None) -> Path | None:
    source = os.environ if env is None else env
    raw = (source.get(CONNECTION_FILE_ENV) or "").strip()
    if raw:
        return Path(raw)
    for name in _DB_ENVS:
        db = (source.get(name) or "").strip()
        if db:
            return Path(db).parent / DEFAULT_NAME
    return None


def _entry(raw: Any) -> dict[str, str] | None:
    """연결 한 벌(url·token·verify_tls·conn_id·updated_at·updated_by). url·token 이 비면 None."""
    if not isinstance(raw, dict):
        return None
    url, token = raw.get("url"), raw.get("token")
    if (
        not isinstance(url, str)
        or not url.strip()
        or not isinstance(token, str)
        or not token
    ):
        return None
    verify = raw.get("verify_tls")
    verify = verify if isinstance(verify, str) else ""
    conn_id = raw.get("conn_id")
    if not isinstance(conn_id, str) or not conn_id:
        conn_id = _hash_conn_id(url.strip())
    return {
        "url": url.strip(),
        "token": token,
        "verify_tls": verify,
        "conn_id": conn_id,
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else "",
        "updated_by": raw.get("updated_by")
        if isinstance(raw.get("updated_by"), str)
        else "",
    }


def _hash_conn_id(url: str) -> str:
    """주소로만 정한다(토큰·TLS 는 같은 Zabbix 를 바꾸지 않는다)."""
    return "zc_" + _url_hash(url)


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()[:12]


def env_conn_id(url: str) -> str:
    """.env 연결(기본 회사만)의 연결 구분값: 'env:' + 주소 해시 12자."""
    return f"{ENV_CONN_ID}:{_url_hash(url)}"


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def read_connection(
    path: Path | None, company: str | None = None, default_company: str | None = None
) -> dict[str, str] | None:
    """연결 파일의 url·token·verify_tls·conn_id. 없거나 깨졌거나 url·token 이 비면 None.

    company 가 None 이면 018 동작(회사 없는 한 벌, 회사별 파일이면 기본 회사 칸).
    company 가 있으면 그 회사 칸만 본다. 018 모양 한 벌은 default_company 것이다.
    """
    raw = _load(path)
    if raw is None:
        return None
    companies = raw.get("companies")
    if isinstance(companies, dict):
        key = company or default_company
        return _entry(companies.get(key)) if key else None
    if company is None or company == default_company:
        return _entry(raw)
    return None


def connection_file_state(path: Path | None) -> str:
    """'missing'(파일 없음) | 'ok' | 'broken'(있는데 JSON·모양이 깨짐)."""
    if path is None or not path.exists():
        return "missing"
    return "ok" if _load(path) is not None else "broken"


def connected_companies(path: Path | None, default_company: str) -> list[str]:
    """연결 파일에 연결이 있는 회사 ID 목록(018 모양 한 벌은 기본 회사)."""
    raw = _load(path)
    if raw is None:
        return []
    companies = raw.get("companies")
    if isinstance(companies, dict):
        return sorted(
            str(k)
            for k, v in companies.items()
            if isinstance(k, str) and COMPANY_ID_RE.match(k) and _entry(v) is not None
        )
    return [default_company] if _entry(raw) is not None else []


def save_connection(
    path: Path,
    url: str,
    token: str,
    verify_tls: str = "",
    updated_by: str = "",
    company: str | None = None,
    default_company: str | None = None,
) -> None:
    """연결 파일을 쓴다(0600, 임시 파일 → 바꿔치기).

    company 가 있으면 그 회사 칸만 바꾼다(다른 회사 칸은 그대로, 018 모양 한 벌은 기본 회사 칸으로 옮긴다).
    주소·토큰·verify_tls 가 그대로면 conn_id 를 유지하고, 하나라도 바뀌면 새로 만든다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    url = url.strip()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = _load(path) or {}
    if company is None:
        old = None if isinstance(raw.get("companies"), dict) else _entry(raw)
    else:
        companies = raw.get("companies")
        if not isinstance(companies, dict):
            companies = {}
            legacy = _entry(raw)
            if legacy is not None and default_company:
                companies[default_company] = legacy
        old = _entry(companies.get(company))
    same = old is not None and old["url"] == url  # 주소가 같으면 같은 Zabbix
    entry = {
        "url": url,
        "token": token,
        "verify_tls": verify_tls,
        "conn_id": old["conn_id"] if same else "zc_" + secrets.token_hex(6),
        "updated_at": now,
        "updated_by": updated_by,
    }
    body: dict[str, Any] = (
        entry if company is None else {"companies": {**companies, company: entry}}
    )
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    os.replace(tmp, path)


def default_company(env: Mapping[str, str]) -> str | None:
    """`DEFAULT_COMPANY_ID`. 없으면 None(회사 나누기 꺼짐)."""
    value = (env.get(DEFAULT_COMPANY_ENV) or "").strip()
    return value or None


def resolve(env: Mapping[str, str]) -> dict[str, str] | None:
    """env 가 가리키는 회사의 연결 (url·token·verify_tls·conn_id). 없으면 None.

    회사 나누기가 켜져 있으면 `ZABBIX_COMPANY`(없으면 기본 회사)의 파일 칸, 없으면 기본 회사만 `.env`(conn_id 'env').
    꺼져 있으면 018 그대로(파일 → `.env`).
    """
    default = default_company(env)
    company = (env.get(COMPANY_ENV) or "").strip() or default
    found = read_connection(connection_path(env), company, default)
    if found is not None:
        return found
    if company != default:
        return None
    url = (env.get("ZABBIX_URL") or "").strip()
    if not url:
        return None
    return {
        "url": url,
        "token": env.get("ZABBIX_API_TOKEN") or "",
        "verify_tls": env.get("ZABBIX_VERIFY_TLS") or "",
        "conn_id": env_conn_id(url),
        "updated_at": "",
        "updated_by": "",
    }


def overlay(env: Mapping[str, str]) -> dict[str, str]:
    """환경 변수 위에 연결 파일 값을 얹은 사본 (파일이 없으면 그대로).

    회사 나누기가 켜져 있고 그 회사 연결이 없으면 ZABBIX_URL·토큰을 비운다(다른 회사 연결로 떨어지지 않는다).
    """
    out = dict(env)
    if default_company(env) is None:
        found = read_connection(connection_path(env))
        if found is not None:
            out["ZABBIX_URL"] = found["url"]
            out["ZABBIX_API_TOKEN"] = found["token"]
            out["ZABBIX_VERIFY_TLS"] = found["verify_tls"]
        return out
    found = resolve(env)
    out["ZABBIX_URL"] = found["url"] if found else ""
    out["ZABBIX_API_TOKEN"] = found["token"] if found else ""
    out["ZABBIX_VERIFY_TLS"] = found["verify_tls"] if found else ""
    return out


def _stamp(path: Path | None) -> tuple[float, int] | None:
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime, st.st_size)


def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 - 닫기 실패가 새 연결을 막지 않게
            pass


class LiveClient:
    """연결 파일이 바뀌면 다음 호출 때 새 클라이언트로 바꾸는 감싸개 (`call` 만 넘긴다)."""

    def __init__(self, build: Callable[[], Any], path: Path | None) -> None:
        self._build = build
        self._path = path
        self._lock = threading.Lock()
        self._stamp = _stamp(path)
        self._client = build()

    @property
    def client(self) -> Any:
        stamp = _stamp(self._path)
        if stamp != self._stamp:
            with self._lock:
                if stamp != self._stamp:
                    old, self._client = self._client, self._build()
                    self._stamp = stamp
                    _close(
                        old
                    )  # 옛 연결(HTTP 연결 풀)을 닫는다. 바꾸는 일은 드물고 조회는 짧다
        return self._client

    @property
    def mock(self) -> bool:
        return bool(getattr(self.client, "mock", False))

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.client.call(method, params)
