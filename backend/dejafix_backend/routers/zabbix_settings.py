"""#28·#29 GET·PUT /api/settings/zabbix  (계약 contracts/api.md #28·#29, 결정 018)

고객사가 화면에서 자기 Zabbix 주소·읽기 전용 API 토큰을 넣는다. 값은 Zabbix 연결 파일
(`Settings.zabbix_connection_path`, 0600)에 두고 libs/zabbix_ro 가 `.env` 보다 먼저 쓴다.
- 저장 전에 그 주소·토큰으로 `apiinfo.version`·`host.get`(1건)을 불러 본다(허용 목록 안, 쓰기 없음).
  실패하면 저장하지 않고 422 ZABBIX_CHECK_FAILED. 이유는 한 줄이고 토큰·응답 본문을 넣지 않는다.
- 저장하면 Backend 의 Zabbix 캐시를 비운다. Scheduler·mcp-zabbix 는 다음 호출 때 파일을 다시 읽는다.
- 토큰은 어떤 응답에도 내보내지 않는다(`token_set` 만).
- 서버가 이 주소로 직접 요청하므로 루프백·링크로컬·지정 안 된 주소(127.0.0.0/8, ::1, 169.254.0.0/16,
  fe80::/10, 0.0.0.0 등)로 풀리는 주소는 막는다. 사설망(10/8 등)은 고객 Zabbix가 있을 수 있어 연다.
  리다이렉트는 따라가지 않는다(zabbix_ro 의 httpx 기본값 follow_redirects=False).
- 토큰 칸을 비우면 저장된 토큰을 다시 쓰는데, 주소가 저장된 주소와 같을 때만이다(저장 토큰을 새 주소로
  보내지 않는다).
"""

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

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


def _truthy_tls(value: str) -> bool:
    """`verify_tls` 글자(파일·.env). 비어 있으면 확인함(기본)."""
    return value.strip().lower() not in ("false", "0", "no", "off")


def _resolve(host: str) -> list[str]:
    """호스트 이름이 풀리는 주소들 (시험이 바꿔 끼운다)."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _blocked(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast


def _host_ok(url: str) -> None:
    """루프백·링크로컬로 풀리는 주소면 422. 이름을 못 풀면 422."""
    host = urlsplit(url).hostname or ""
    if not host:
        raise ApiError(422, "VALIDATION_ERROR", "Zabbix 주소에 서버 이름이 없습니다")
    try:
        addresses = _resolve(host)
    except OSError:
        raise ApiError(
            422, "ZABBIX_CHECK_FAILED", "Zabbix 서버 이름을 찾지 못했습니다"
        ) from None
    if not addresses or any(_blocked(a) for a in addresses):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "이 서버 자신이나 링크로컬 주소로는 연결할 수 없습니다",
        )


def _state(settings: Settings) -> dict[str, Any]:
    found = zabbix_ro.read_connection(settings.zabbix_connection_path)
    base = {"verify_tls": True, "mock": settings.zabbix_mock}
    if found is not None:
        verify = _truthy_tls(found["verify_tls"])
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
            "verify_tls": _truthy_tls(settings.zabbix_verify_tls),
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
    await run_in_threadpool(_host_ok, url)
    token = body.token.strip()
    if not token:
        saved = zabbix_ro.read_connection(settings.zabbix_connection_path)
        if saved and saved["url"] != url:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Zabbix 주소를 바꿀 때는 그 주소의 토큰을 다시 넣어 주세요",
            )
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
