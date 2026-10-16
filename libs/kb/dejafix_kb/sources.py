"""지식 출처 수집기 (FR-RAG-002). 원문을 SourceDoc 으로 모은다. 어떤 DB에도 쓰지 않는다.

출처
- incident_report: shared.db 장애 + 최신 리포트(요약·원인) + 변경 계획 단계 (장애 1건 = 문서 1개)
- runbook: KB_DOC_DIRS 의 마크다운 문서
- pack_action: packs/<DOMAIN_PACK>/actions.yaml 의 동작 설명(제목·티어·효과·위험·사전 확인·롤백)
- resolution_note: 사람이 쓴 해결 메모 — backend.db resolution_notes(있을 때만, FR-RAG-010)
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .config import KbSettings
from .redact import redact, redact_value


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SourceDoc:
    source_type: str  # incident_report | runbook | pack_action | resolution_note
    source_id: (
        str  # 출처 안에서의 고유 키 (incident:12, docs/demo/README.md, action:<id>)
    )
    title: str
    text: str  # 마크다운 원문
    collected_at: str = field(default_factory=now_iso)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _json_list(value: str | None) -> list[Any]:
    try:
        data = json.loads(value) if value else []
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def incident_docs(shared_db: Path) -> list[SourceDoc]:
    """리포트가 있는 장애마다 문서 1개. shared.db 가 없으면 빈 목록."""
    if not shared_db.exists():
        return []
    conn = _ro(shared_db)
    try:
        rows = conn.execute(
            """SELECT i.id, i.host_name, i.title, i.severity, i.status, i.started_at, i.resolved_at,
                      r.id AS report_id, r.kind, r.summary, r.causes_json, r.created_at
                 FROM incidents i
                 JOIN analysis_reports r ON r.incident_id = i.id
                WHERE r.version = (SELECT MAX(version) FROM analysis_reports a
                                    WHERE a.incident_id = i.id)
                ORDER BY i.id"""
        ).fetchall()
        docs = []
        for r in rows:
            lines = [
                f"# 장애 #{r['id']} {r['title']}",
                f"- 호스트: {r['host_name'] or '확인할 수 없음'} · 심각도 {r['severity']} · 상태 {r['status']}",
                f"- 시작 {r['started_at']} · 해결 {r['resolved_at'] or '미해결'}",
                f"- 리포트 #{r['report_id']} ({r['kind']}): {r['summary']}",
            ]
            for c in _json_list(r["causes_json"]):
                if isinstance(c, dict):
                    lines.append(
                        f"- 원인 후보 {c.get('rank')}: {c.get('title')} (확신도 {c.get('confidence')})"
                    )
            plan = conn.execute(
                "SELECT id FROM change_plans WHERE report_id = ? ORDER BY id DESC LIMIT 1",
                (r["report_id"],),
            ).fetchone()
            if plan:
                for s in conn.execute(
                    "SELECT seq, tier, title FROM plan_steps WHERE plan_id = ? ORDER BY seq",
                    (plan["id"],),
                ):
                    lines.append(
                        f"- 계획 {s['seq']}단계 [{s['tier']}] {s['title']} (미리보기)"
                    )
            docs.append(
                SourceDoc(
                    "incident_report",
                    f"incident:{r['id']}",
                    f"장애 #{r['id']} {r['title']}",
                    "\n".join(lines),
                    meta={
                        "incident_id": r["id"],
                        "report_id": r["report_id"],
                        "host_name": r["host_name"],
                        "severity": r["severity"],
                        "status": r["status"],
                    },
                )
            )
        return docs
    finally:
        conn.close()


def runbook_docs(root: Path, dirs: tuple[str, ...]) -> list[SourceDoc]:
    docs = []
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root).as_posix()
            title = next(
                (
                    ln.lstrip("#").strip()
                    for ln in text.splitlines()
                    if ln.startswith("#")
                ),
                rel,
            )
            docs.append(SourceDoc("runbook", rel, title, text, meta={"path": rel}))
    return docs


def pack_docs(root: Path, domain_pack: str | None) -> list[SourceDoc]:
    """팩 동작 설명. 팩 이름은 DOMAIN_PACK 으로만 받는다(엔진에 팩 이름을 두지 않음)."""
    if not domain_pack:
        return []
    path = root / "packs" / domain_pack / "actions.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = []
    for a in data.get("actions") or []:
        lines = [
            f"# 동작 {a.get('id')} — {a.get('title')}",
            f"- 티어 {a.get('tier')} (규칙 파일이 정함)",
        ]
        for key, label in (
            ("expected_effect", "예상 효과"),
            ("risk", "위험"),
            ("precheck", "사전 확인"),
            ("rollback", "롤백"),
        ):
            if a.get(key):
                lines.append(f"- {label}: {a[key]}")
        docs.append(
            SourceDoc(
                "pack_action",
                f"action:{a.get('id')}",
                str(a.get("title")),
                "\n".join(lines),
                meta={
                    "action_id": a.get("id"),
                    "tier": a.get("tier"),
                    "pack": domain_pack,
                },
            )
        )
    return docs


NOTES_TABLE = "resolution_notes"
# Issue #153 제안 DDL 기준. contracts/db-schema.sql 계약 PR(DB 담당)이 머지되면 그 이름에 맞춘다
NOTES_COLUMNS = (
    "id",
    "incident_id",
    "root_cause",
    "action_taken",
    "result",
    "created_at",
)
log = logging.getLogger(__name__)


def note_docs(backend_db: Path) -> list[SourceDoc]:
    """사람이 쓴 해결 메모. 테이블이 아직 없으면(Backend 미구현) 빈 목록. AI 가 쓴 문장은 없다."""
    if not backend_db.exists():
        return []
    conn = _ro(backend_db)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (NOTES_TABLE,),
        ).fetchone()
        if not exists:
            return []
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({NOTES_TABLE})")}
        missing = [c for c in NOTES_COLUMNS if c not in cols]
        if missing:
            # 컬럼 이름이 다르면 해결 메모만 건너뛴다(장애·런북 색인은 계속)
            log.warning(
                "resolution_notes 컬럼이 예상과 달라 해결 메모 색인을 건너뜀: 없는 컬럼 %s",
                ",".join(missing),
            )
            return []
        rows = conn.execute(
            f"SELECT {', '.join(NOTES_COLUMNS)} FROM {NOTES_TABLE} ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    docs = []
    for r in rows:
        lines = [f"# 해결 메모 #{r['id']} (장애 #{r['incident_id']})"]
        for key, label in (
            ("root_cause", "실제 원인"),
            ("action_taken", "한 조치"),
            ("result", "결과"),
        ):
            if r[key]:
                lines.append(f"- {label}: {r[key]}")
        lines.append(f"- 작성 시각: {r['created_at']}")
        docs.append(
            SourceDoc(
                "resolution_note",
                f"note:{r['id']}",
                f"해결 메모 #{r['id']} (장애 #{r['incident_id']})",
                "\n".join(lines),
                meta={"incident_id": r["incident_id"], "note_id": r["id"]},
            )
        )
    return docs


def collect(settings: KbSettings) -> list[SourceDoc]:
    """출처 전부. 순서: 장애 → 해결 메모 → 런북 → 팩 동작.

    색인에 넣기 전에 제목·본문·meta 의 IP·비밀값을 가린다(NFR-RAG-001). 원본은 바꾸지 않는다.
    """
    docs = (
        incident_docs(settings.path(settings.shared_db_path))
        + note_docs(settings.path(settings.backend_db_path))
        + runbook_docs(settings.root, settings.doc_dirs)
        + pack_docs(settings.root, settings.domain_pack)
    )
    for d in docs:
        d.title = redact(d.title)
        d.text = redact(d.text)
        d.meta = redact_value(d.meta)
    return docs
