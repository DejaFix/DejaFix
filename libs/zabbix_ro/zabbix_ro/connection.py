"""화면에서 정한 Zabbix 연결 (연결 파일).

`ZABBIX_CONNECTION_FILE`(없으면 `BACKEND_DB_PATH`·`SHARED_DB_PATH` 옆 `zabbix_connection.json`) JSON 파일에 `{url, token, verify_tls}` 가 있으면 `from_env` 가
`ZABBIX_URL`·`ZABBIX_API_TOKEN`·`ZABBIX_VERIFY_TLS` 대신 이 값을 쓴다. 파일이 없거나 깨졌으면 환경 변수 그대로.
- 쓰는 쪽은 Backend 관리자 API(`PUT /api/settings/zabbix`)뿐이다. 파일은 0600, 임시 파일 → os.replace.
- 토큰은 파일에만 두고 로그·예외 문장에 넣지 않는다.
- `LiveClient` 는 파일이 바뀌면(수정 시각·크기) 다음 호출 때 클라이언트를 새로 만든다.
  Scheduler·mcp-zabbix 처럼 클라이언트를 오래 들고 있는 쪽이 재시작 없이 새 연결을 따른다.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONNECTION_FILE_ENV = "ZABBIX_CONNECTION_FILE"


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


def read_connection(path: Path | None) -> dict[str, str] | None:
    """연결 파일의 url·token·verify_tls. 없거나 깨졌거나 url·token 이 비면 None."""
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
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
    return {
        "url": url.strip(),
        "token": token,
        "verify_tls": verify if isinstance(verify, str) else "",
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else "",
        "updated_by": raw.get("updated_by")
        if isinstance(raw.get("updated_by"), str)
        else "",
    }


def save_connection(
    path: Path, url: str, token: str, verify_tls: str = "", updated_by: str = ""
) -> None:
    """연결 파일을 쓴다(0600, 임시 파일 → 바꿔치기)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "url": url.strip(),
        "token": token,
        "verify_tls": verify_tls,
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_by": updated_by,
    }
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    os.replace(tmp, path)


def overlay(env: Mapping[str, str]) -> dict[str, str]:
    """환경 변수 위에 연결 파일 값을 얹은 사본 (파일이 없으면 그대로)."""
    out = dict(env)
    found = read_connection(connection_path(env))
    if found is not None:
        out["ZABBIX_URL"] = found["url"]
        out["ZABBIX_API_TOKEN"] = found["token"]
        out["ZABBIX_VERIFY_TLS"] = found["verify_tls"]
    return out


def _stamp(path: Path | None) -> tuple[float, int] | None:
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime, st.st_size)


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
                    self._client = self._build()
                    self._stamp = stamp
        return self._client

    @property
    def mock(self) -> bool:
        return bool(getattr(self.client, "mock", False))

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.client.call(method, params)
