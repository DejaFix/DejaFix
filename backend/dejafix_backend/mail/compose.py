"""메일 제목·본문 (T39, FR-MAIL-005).

본문은 Agent 가 저장한 리포트·계획 값을 옮겨 적기만 한다. 원인·티어·분석 문장을 새로
만들거나 바꾸지 않는다 (NFR-MAINT-010). 여기 있는 고정 문구는 항목 이름과 안내뿐이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from dejafix_backend.routers.incidents import SEVERITY_LABELS

KST = timezone(timedelta(hours=9))
FALLBACK_LABEL = "[LLM 미연결 — 규칙 기반 최소 리포트]"
PREVIEW_NOTE = "미리보기 — 실행되지 않음"


@dataclass
class ReportMail:
    incident_id: int
    report_id: int
    report_kind: str
    title: str
    host_name: str | None
    severity: int
    started_at: str
    summary: str
    causes: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    unknowns: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    max_tier: str | None = None


def _loads(text: str | None, default: Any) -> Any:
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def from_rows(report: Any, steps: list[Any], max_tier: str | None = None) -> ReportMail:
    """shared.analysis_reports·incidents JOIN 행, plan_steps 행, change_plans.max_tier → ReportMail."""
    return ReportMail(
        incident_id=report["incident_id"],
        report_id=report["report_id"],
        report_kind=report["kind"],
        title=report["title"],
        host_name=report["host_name"],
        severity=report["severity"],
        started_at=report["started_at"],
        summary=report["summary"],
        causes=_loads(report["causes_json"], []),
        facts=_loads(report["facts_json"], []),
        unknowns=_loads(report["unknowns_json"], []),
        steps=[dict(s) for s in steps],
        max_tier=max_tier,
    )


def to_kst(iso: str | None) -> str:
    if not iso:
        return "확인할 수 없음"
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return iso
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def severity_label(level: int) -> str:
    return SEVERITY_LABELS.get(level, str(level))


def subject(mail: ReportMail) -> str:
    host = mail.host_name or "호스트 확인 불가"
    return f"[DejaFix][{severity_label(mail.severity)}] {host} - {mail.title}"


def incident_link(base_url: str, incident_id: int) -> str:
    base = base_url.strip().rstrip("/")
    if not base or "<" in base:
        return "(링크 주소 미설정 — APP_BASE_URL, TODO: 추후결정)"
    return f"{base}/incidents/{incident_id}"


def body(mail: ReportMail, base_url: str, sent_at: datetime) -> str:
    lines: list[str] = []
    lines.append(f"장애: {mail.title}")
    lines.append(f"호스트: {mail.host_name or '확인할 수 없음'}")
    lines.append(f"심각도: {severity_label(mail.severity)}")
    lines.append("")
    # ① 리포트 종류
    lines.append(
        "① 리포트: "
        + (FALLBACK_LABEL if mail.report_kind == "fallback" else "AI 분석 리포트")
    )
    # ② 요약
    lines.append(f"② 요약: {mail.summary}")
    # ③ 원인 후보 TOP3 (확신도는 저장된 문자 그대로)
    lines.append("③ 원인 후보")
    if mail.causes:
        for cause in sorted(mail.causes, key=lambda c: c.get("rank", 99))[:3]:
            lines.append(
                f"   {cause.get('rank', '-')}. {cause.get('title', '')}"
                f" (확신도: {cause.get('confidence', '확인할 수 없음')})"
            )
    else:
        lines.append("   (저장된 원인 후보 없음)")
    # ④ 확인할 수 없음
    lines.append("④ 확인할 수 없음")
    unknown_lines = [
        f"   - {u.get('label', '')} · {u.get('reason', '')}" for u in mail.unknowns
    ] + [
        f"   - {f.get('label', '')} · {f.get('unknown_reason', '')}"
        for f in mail.facts
        if f.get("value") is None
    ]
    lines.extend(unknown_lines or ["   (없음)"])
    # ⑤ 계획 단계 (티어는 저장된 값 그대로)
    lines.append(f"⑤ 변경 계획 ({PREVIEW_NOTE})")
    if mail.steps:
        lines.append(
            f"   단계 {len(mail.steps)}개 · 최고 티어 {mail.max_tier or '확인할 수 없음'}"
        )
        for step in mail.steps:
            lines.append(
                f"   {step.get('seq', '-')}. [{step.get('tier', '?')}] {step.get('title', '')}"
            )
    else:
        lines.append("   (저장된 계획 없음)")
    # ⑥ 링크
    lines.append(f"⑥ 장애 상세: {incident_link(base_url, mail.incident_id)}")
    # ⑦ 시각 (KST)
    lines.append(
        f"⑦ 장애 시작: {to_kst(mail.started_at)} / 발송: "
        f"{sent_at.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}"
    )
    lines.append("")
    lines.append(
        "이 메일은 DejaFix가 자동으로 보냈습니다. 계획은 미리보기이며 어떤 조치도 실행하지 않았습니다."
    )
    return "\n".join(lines)
