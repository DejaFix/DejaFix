"""#26·#27 GET·POST /api/incidents/{id}/notes — 해결 메모 ([이후], Issue #153)

장애가 해결된 뒤 **사람이** 적는 "실제 원인·한 조치·결과"를 backend.db `resolution_notes` 에 저장한다.
- 작성자(author_user_id)는 요청 본문이 아니라 로그인한 사용자 토큰에서만 채운다(AI·내부 호출이 대신 쓸 수 없음).
- shared.db 는 장애 존재 확인용 읽기만 한다(ATTACH ro 유지). 실행·run 필드는 없고 수정·삭제 API 도 없다.
- 비밀값·IP 가리기는 색인 단계에서 하므로 사람이 쓴 원문을 그대로(앞뒤 공백만 잘라) 저장한다.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from dejafix_backend.db import Db
from dejafix_backend.deps import get_db, require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError
from dejafix_backend.timeutil import utc_now_iso

router = APIRouter(prefix="/incidents", tags=["notes"])

MAX_NOTE_CHARS = 1000


class NoteRequest(BaseModel):
    # author_user_id 등 알 수 없는 키는 무시한다(작성자는 토큰에서만)
    model_config = ConfigDict(extra="ignore")

    root_cause: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)
    action_taken: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)
    result: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)


def _require_incident(db: Db, incident_id: int) -> None:
    if not db.shared_ok:
        raise ApiError(
            503, "SHARED_DB_UNAVAILABLE", "공유 DB가 아직 준비되지 않았습니다"
        )
    found = db.conn.execute(
        "SELECT 1 FROM shared.incidents WHERE id = ?", (incident_id,)
    ).fetchone()
    if found is None:
        raise ApiError(404, "NOT_FOUND", "장애를 찾을 수 없습니다")


_NOTE_SQL = """
SELECT n.id, n.incident_id, n.root_cause, n.action_taken, n.result, n.created_at,
       u.id AS author_id, COALESCE(NULLIF(u.display_name, ''), u.username) AS author_name
FROM resolution_notes n JOIN users u ON u.id = n.author_user_id
"""


def _note(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "incident_id": row["incident_id"],
        "root_cause": row["root_cause"],
        "action_taken": row["action_taken"],
        "result": row["result"],
        "author": {"id": row["author_id"], "display_name": row["author_name"]},
        "created_at": row["created_at"],
    }


@router.get("/{incident_id}/notes")
def list_notes(
    incident_id: int,
    _: dict = Depends(require_role("viewer")),
    db: Db = Depends(get_db),
):
    _require_incident(db, incident_id)
    rows = db.conn.execute(
        _NOTE_SQL + " WHERE n.incident_id = ? ORDER BY n.created_at DESC, n.id DESC",
        (incident_id,),
    ).fetchall()
    return ok([_note(r) for r in rows])


@router.post("/{incident_id}/notes", status_code=201)
def create_note(
    incident_id: int,
    body: NoteRequest,
    user: dict = Depends(require_role("operator")),
    db: Db = Depends(get_db),
):
    values = {
        key: (text.strip() or None) if text is not None else None
        for key, text in body.model_dump().items()
    }
    if all(v is None for v in values.values()):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "root_cause·action_taken·result 중 하나는 내용이 있어야 합니다",
        )
    _require_incident(db, incident_id)
    cur = db.conn.execute(
        "INSERT INTO resolution_notes (incident_id, author_user_id, root_cause,"
        " action_taken, result, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            incident_id,
            user["id"],
            values["root_cause"],
            values["action_taken"],
            values["result"],
            utc_now_iso(),
        ),
    )
    db.conn.commit()
    row = db.conn.execute(_NOTE_SQL + " WHERE n.id = ?", (cur.lastrowid,)).fetchone()
    return ok(_note(row))
