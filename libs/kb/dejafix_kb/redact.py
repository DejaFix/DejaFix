"""색인·임베딩 전 가리기 (NFR-RAG-001, 결정 017 "외부로 보내기 전에 가린다").

지식 저장소·검색 결과·외부 /embeddings·LLM 프롬프트로 사설 주소·비밀값이 나가지 않게 한다.
원문 파일·DB는 바꾸지 않고, 색인·전송하는 사본만 가린다.

- 개인 키 블록(-----BEGIN ... PRIVATE KEY----- ~ END) → `<REDACTED KEY>`
- `Bearer <토큰>` → `Bearer <REDACTED>`
- 키=값: 이름에 password·passwd·pwd·secret·token·api_key·apikey 가 들어가면(SMTP_PASSWORD 처럼 접두사가 붙어도)
  값만 `<REDACTED>`. 한글 키(비밀번호·암호·토큰)도 같다
- 이메일 → `<EMAIL>`, IPv4·IPv6 → `<IP>`
- 숫자와 영문이 섞인 32자 이상 덩어리(API 토큰 형태) → `<REDACTED>`
  근거 ID(`ev_` + 10자리, `kb_` + 12자리)는 32자보다 짧아 영향이 없다
"""

from __future__ import annotations

import re
from typing import Any

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.S,
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_KEY_NAME = r"[A-Za-z0-9_.-]*?(?:password|passwd|pwd|secret|token|api[_-]?key|apikey)[A-Za-z0-9_.-]*"
_KV = re.compile(
    r"(?i)(?<![A-Za-z0-9])(" + _KEY_NAME + r")(\s*[:=]\s*)(['\"]?)([^\s'\"`,]+)"
)
_KV_KO = re.compile(
    r"(비밀번호|암호|토큰|인증키|API ?키)(\s*[:=]\s*)(['\"]?)([^\s'\"`,]+)"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_IPV4 = re.compile(
    r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
)
# 5묶음 이상이거나 '::' 가 들어간 형태만 IPv6 로 본다(12:30:45 같은 시각은 제외)
_IPV6_FULL = re.compile(
    r"(?<![\w:])(?:[0-9A-Fa-f]{1,4}:){4,7}[0-9A-Fa-f]{1,4}(?![\w:])"
)
_IPV6_SHORT = re.compile(
    r"(?<![\w:])(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5})?(?![\w:])"
)
_LONG = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")


def _long_token(m: re.Match) -> str:
    s = m.group(0)
    # 영문 단어·경로처럼 보이는 것은 두고, 숫자와 문자가 섞인 덩어리만 가린다
    return "<REDACTED>" if re.search(r"\d", s) and re.search(r"[A-Za-z]", s) else s


def _kv(m: re.Match) -> str:
    return f"{m.group(1)}{m.group(2)}{m.group(3)}<REDACTED>"


def redact(text: str) -> str:
    if not text:
        return text
    text = _PRIVATE_KEY.sub("<REDACTED KEY>", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} <REDACTED>", text)
    text = _KV.sub(_kv, text)
    text = _KV_KO.sub(_kv, text)
    text = _EMAIL.sub("<EMAIL>", text)
    text = _IPV6_FULL.sub("<IP>", text)
    text = _IPV6_SHORT.sub("<IP>", text)
    text = _IPV4.sub("<IP>", text)
    return _LONG.sub(_long_token, text)


def redact_value(value: Any) -> Any:
    """meta 같은 중첩 값의 문자열을 모두 가린다."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
