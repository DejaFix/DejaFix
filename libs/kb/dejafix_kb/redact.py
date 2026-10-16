"""색인 전 가리기 (NFR-RAG-001). 지식 저장소·검색 결과·LLM 프롬프트로 사설 주소·비밀값이 나가지 않게 한다.

- IPv4 주소 → `<IP>`
- `Bearer <토큰>`, `password|passwd|pwd|secret|token|api_key|apikey = 값` → 값만 `<REDACTED>`
- 32자 이상 16진수·base64url 덩어리(API 토큰 형태) → `<REDACTED>`
- 이메일 주소 → `<EMAIL>`
원문 파일·DB는 바꾸지 않고, 색인에 넣는 사본만 가린다.
"""

from __future__ import annotations

import re

_IPV4 = re.compile(
    r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_KV = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|app[_ ]password)(\s*[:=]\s*)(['\"]?)([^\s'\"`,]+)"
)
_LONG = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def _long_token(m: re.Match) -> str:
    s = m.group(0)
    # 영문 단어·경로처럼 보이는 것은 두고, 숫자와 문자가 섞인 덩어리만 가린다
    return "<REDACTED>" if re.search(r"\d", s) and re.search(r"[A-Za-z]", s) else s


def redact(text: str) -> str:
    text = _BEARER.sub(lambda m: f"{m.group(1)} <REDACTED>", text)
    text = _KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}<REDACTED>", text)
    text = _EMAIL.sub("<EMAIL>", text)
    text = _IPV4.sub("<IP>", text)
    return _LONG.sub(_long_token, text)
