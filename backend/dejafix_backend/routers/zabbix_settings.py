"""#28·#29 GET·PUT /api/settings/zabbix  (계약 contracts/api.md #28·#29, 결정 018)

고객사가 화면에서 자기 Zabbix 주소·읽기 전용 API 토큰을 넣는다. 값은 Zabbix 연결 파일
(`Settings.zabbix_connection_path`, 0600)에 두고 libs/zabbix_ro 가 `.env` 보다 먼저 쓴다.
- 저장 전에 그 주소·토큰으로 `apiinfo.version`·`host.get`(1건)을 불러 본다(허용 목록 안, 쓰기 없음).
  실패하면 저장하지 않고 422 ZABBIX_CHECK_FAILED. 이유는 한 줄이고 토큰·응답 본문을 넣지 않는다.
- 저장하면 Backend 의 Zabbix 캐시를 비운다. Scheduler·mcp-zabbix 는 다음 호출 때 파일을 다시 읽는다.
- 토큰은 어떤 응답에도 내보내지 않는다(`token_set` 만).
"""

import asyncio
from typing import Any

import zabbix_ro
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from dejafix_backend import zabbix
from dejafix_backend.config import Settings, get_settings
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError

router = APIRouter(prefix="/settings", tags=["settings"])

CHECK_TIMEOUT_SEC = 10.0


class ZabbixIn(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    token: str = Field(default="", max_length=512)
    verify_tls: bool = True


def _state(settings: Settings) -> dict[str, Any]:
    found = zabbix_ro.read_connection(settings.zabbix_connection_path)
    base = {"verify_tls": True, "mock": settings.zabbix_mock}
    if found is not None:
        verify = found["verify_tls"].strip().lower() not in ("false", "0", "no", "off")
        return {
            **base,
            "source": "file",
            "url": found["url"],
            "token_set": True,
            "verify_tls": verify,
            "updated_at": found["updated_at"] or None,
            "updated_by": found["updated_by"] or None,
        }
    if settings.zabbix_url.strip():
        return {
            **base,
            "source": "env",
            "url": settings.zabbix_url.strip(),
            "token_set": bool(settings.zabbix_api_token),
            "updated_at": None,
            "updated_by": None,
        }
    return {
        **base,
        "source": "none",
        "url": None,
        "token_set": False,
        "updated_at": None,
        "updated_by": None,
    }


def _check(url: str, token: str, verify_tls: bool) -> None:
    """그 주소·토큰으로 조회 두 번. 실패하면 ZabbixRoError."""
    client = zabbix_ro.from_env(
        {
            "ZABBIX_MOCK": "false",
            "ZABBIX_URL": url,
            "ZABBIX_API_TOKEN": token,
            "ZABBIX_VERIFY_TLS": "true" if verify_tls else "false",
        }
    )
    client.call("apiinfo.version", {})
    client.call("host.get", {"output": ["hostid"], "limit": 1})


def _reason(exc: Exception, token: str) -> str:
    text = str(exc).replace(token, "***") if token else str(exc)
    return text.splitlines()[0][:200] if text else type(exc).__name__


@router.get("/zabbix")
async def get_zabbix(
    _: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
):
    return ok(_state(settings))


@router.put("/zabbix")
async def put_zabbix(
    body: ZabbixIn,
    user: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
):
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Zabbix 주소는 http:// 또는 https:// 로 시작해야 합니다",
        )
    token = body.token.strip()
    if not token:
        saved = zabbix_ro.read_connection(settings.zabbix_connection_path)
        token = saved["token"] if saved else ""
    if not token:
        raise ApiError(
            422, "VALIDATION_ERROR", "Zabbix 읽기 전용 API 토큰을 넣어 주세요"
        )
    try:
        await asyncio.wait_for(
            run_in_threadpool(_check, url, token, body.verify_tls),
            timeout=CHECK_TIMEOUT_SEC,
        )
    except TimeoutError:
        raise ApiError(
            422,
            "ZABBIX_CHECK_FAILED",
            f"Zabbix가 {CHECK_TIMEOUT_SEC:g}초 안에 답하지 않았습니다",
        ) from None
    except zabbix_ro.ZabbixRoError as exc:
        raise ApiError(
            422,
            "ZABBIX_CHECK_FAILED",
            f"Zabbix에 연결하지 못했습니다: {_reason(exc, token)}",
        ) from None
    await run_in_threadpool(
        zabbix_ro.save_connection,
        settings.zabbix_connection_path,
        url,
        token,
        "true" if body.verify_tls else "false",
        str(user.get("username") or ""),
    )
    zabbix.reset()  # 새 연결로 다시 읽게 캐시를 비운다
    return ok(_state(settings))
