"""검수 워크플로우 (PRD F-08-1 ~ F-08-4).

- 자동 생성 프로파일은 '미검수'로 시작하고, 모든 사실 항목을 승인·수정·삭제로 처리해야 '검수완료'가 된다.
- 수정한 항목은 manually_edited=True 가 되어 자동 갱신이 덮어쓰지 않는다. 자동 갱신이 다른 값을
  가져오면 ReviewQueue '충돌 알림'으로 올라온다 (F-08-4, core/ingest.py).
- 검수자·일시·수정 전후 값은 ReviewLog 와 AuditLog 에 남는다 (F-08-3).
- 전문분야는 core/expertise 의 확정·삭제 경로를 그대로 사용한다(ExpertiseHistory 유지).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from core import constants as C
from core import expertise as EXP
from core.audit import log_change
from data.models import (
    Achievement,
    Directorship,
    Expertise,
    Person,
    Position,
    Reputation,
    ReviewLog,
    ReviewQueue,
)
from data.session import session_scope

ENTITIES: dict[str, type] = {
    "position": Position,
    "directorship": Directorship,
    "reputation": Reputation,
    "achievement": Achievement,
    "expertise": Expertise,
}
ENTITY_LABELS = {
    "position": "경력",
    "directorship": "타사 등기임원",
    "reputation": "평판",
    "achievement": "업적",
    "expertise": "전문분야",
}
_PK = {
    "position": "position_id",
    "directorship": "directorship_id",
    "reputation": "reputation_id",
    "achievement": "achievement_id",
    "expertise": "expertise_id",
}

# 검수자가 고칠 수 있는 필드와 형식. 출처(source_id)는 고칠 수 없다 — 값만 고치고 근거는 유지한다.
EDITABLE: dict[str, dict[str, str]] = {
    "position": {"org_name": "str", "title": "str", "duties": "str", "start_date": "date",
                 "end_date": "date", "term_end_date": "date", "is_registered_officer": "bool"},
    "directorship": {"company_name": "str", "role_type": "str", "appointed_date": "date",
                     "term_end_date": "date", "board_attendance_rate": "float", "listed_yn": "bool"},
    "reputation": {"summary": "str", "status": "str", "verified_yn": "bool", "event_date": "date"},
    "achievement": {"description": "str", "quantitative_metric": "str", "period": "str"},
    "expertise": {"evidence_snippet": "str"},
}
REQUIRED_TEXT = {("position", "org_name"), ("position", "title"), ("directorship", "company_name"),
                 ("directorship", "role_type"), ("reputation", "summary"), ("achievement", "description"),
                 ("expertise", "evidence_snippet")}


@dataclass(frozen=True)
class ReviewProgress:
    total: int
    processed: int

    @property
    def done(self) -> bool:
        return self.total == self.processed


def _path(entity: str, entity_id: int) -> str:
    return f"{entity}:{entity_id}"


def _convert(kind: str, value: Any) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if kind == "str":
        return str(value).strip()
    if kind == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value).strip())
    if kind == "float":
        v = float(value)
        if not 0.0 <= v <= 1.0:
            raise ValueError("출석률은 0~1 사이 값이어야 합니다.")
        return v
    if kind == "bool":
        return value if isinstance(value, bool) else str(value).strip().lower() in ("true", "1", "y", "예")
    raise ValueError(kind)  # pragma: no cover


def _get(s, person_id: int, entity: str, entity_id: int):
    model = ENTITIES.get(entity)
    if model is None:
        raise ValueError(f"검수 대상이 아닌 항목입니다: {entity}")
    row = s.get(model, entity_id)
    if row is None or row.person_id != person_id:
        raise LookupError(f"항목을 찾을 수 없습니다: {entity}/{entity_id}")
    return row


def _log(s, person_id: int, path: str, action: str, before: str | None, after: str | None, user_id: int | None):
    s.add(ReviewLog(person_id=person_id, field_path=path, action=action,
                    before_value=before, after_value=after, reviewer_id=user_id))


def items_of(person_id: int) -> list[tuple[str, Any]]:
    """검수 대상 항목 (entity, row). 화면은 자동값 | 원문 근거 | 처리 3분할로 보여준다."""
    out: list[tuple[str, Any]] = []
    with session_scope() as s:
        for entity, model in ENTITIES.items():
            for row in s.execute(select(model).where(model.person_id == person_id)).scalars():
                out.append((entity, row))
    return out


def processed_paths(person_id: int) -> set[str]:
    """승인 또는 수정된 항목 경로."""
    with session_scope() as s:
        rows = s.execute(
            select(ReviewLog.field_path).where(
                ReviewLog.person_id == person_id,
                ReviewLog.action.in_((C.REVIEW_APPROVE, C.REVIEW_EDIT)),
            )
        ).scalars()
        return set(rows)


def progress(person_id: int) -> ReviewProgress:
    items = items_of(person_id)
    done = processed_paths(person_id)
    paths = {_path(e, getattr(r, _PK[e])) for e, r in items}
    return ReviewProgress(total=len(paths), processed=len(paths & done))


def approve(person_id: int, entity: str, entity_id: int, user_id: int | None) -> None:
    if entity == "expertise":
        with session_scope() as s:
            code = _get(s, person_id, entity, entity_id).taxonomy_code
        EXP.confirm(person_id, code, user_id)
    with session_scope() as s:
        _get(s, person_id, entity, entity_id)
        _log(s, person_id, _path(entity, entity_id), C.REVIEW_APPROVE, None, None, user_id)
    log_change(user_id, "review", C.REVIEW_APPROVE, _path(entity, entity_id), f"person={person_id}")


def edit(person_id: int, entity: str, entity_id: int, field: str, value: Any, user_id: int | None) -> None:
    kind = EDITABLE.get(entity, {}).get(field)
    if kind is None:
        raise ValueError(f"수정할 수 없는 항목입니다: {entity}.{field}")
    new = _convert(kind, value)
    if (entity, field) in REQUIRED_TEXT and not new:
        raise ValueError("필수 항목은 비울 수 없습니다.")
    with session_scope() as s:
        row = _get(s, person_id, entity, entity_id)
        before = getattr(row, field)
        if before == new:
            return
        setattr(row, field, new)
        row.manually_edited = True
        if entity == "expertise":
            row.confirmed_by_user_yn = True
        _log(s, person_id, _path(entity, entity_id), C.REVIEW_EDIT, f"{field}={before}", f"{field}={new}", user_id)
    log_change(user_id, "review", C.REVIEW_EDIT, _path(entity, entity_id), f"{field}: {before} → {new}")


def delete(person_id: int, entity: str, entity_id: int, user_id: int | None, reason: str) -> None:
    if not reason or not reason.strip():
        raise ValueError("삭제 사유를 입력하세요.")
    if entity == "expertise":
        with session_scope() as s:
            code = _get(s, person_id, entity, entity_id).taxonomy_code
        EXP.remove(person_id, code, user_id, reason)
        with session_scope() as s:
            _log(s, person_id, _path(entity, entity_id), C.REVIEW_DELETE, code, reason.strip(), user_id)
    else:
        with session_scope() as s:
            row = _get(s, person_id, entity, entity_id)
            summary = str({k: getattr(row, k) for k in EDITABLE[entity]})
            s.delete(row)
            _log(s, person_id, _path(entity, entity_id), C.REVIEW_DELETE, summary, reason.strip(), user_id)
    log_change(user_id, "review", C.REVIEW_DELETE, _path(entity, entity_id), reason.strip())


def complete(person_id: int, user_id: int | None) -> None:
    """모든 항목이 처리되어야 검수완료로 바꾼다 (F-08-1). 미해결 충돌 알림이 있어도 거부한다."""
    prog = progress(person_id)
    if not prog.done:
        raise ValueError(f"미처리 항목 {prog.total - prog.processed}건이 남아 있습니다.")
    if open_alerts(person_id):
        raise ValueError("해결되지 않은 충돌 알림이 있습니다. 먼저 처리하세요.")
    with session_scope() as s:
        person = s.get(Person, person_id)
        if person is None:
            raise LookupError(f"후보를 찾을 수 없습니다: {person_id}")
        person.profile_status = C.PROFILE_REVIEWED
        _log(s, person_id, "profile", C.REVIEW_APPROVE, C.PROFILE_UNREVIEWED, C.PROFILE_REVIEWED, user_id)
    log_change(user_id, "review", "complete", str(person_id))


def reopen(person_id: int, user_id: int | None, reason: str) -> None:
    """검수완료를 되돌린다(예: 새 자료 반영). 되돌리면 외부 출력이 다시 차단된다."""
    if not reason or not reason.strip():
        raise ValueError("재검수 사유를 입력하세요.")
    with session_scope() as s:
        person = s.get(Person, person_id)
        if person is None:
            raise LookupError(f"후보를 찾을 수 없습니다: {person_id}")
        person.profile_status = C.PROFILE_UNREVIEWED
        _log(s, person_id, "profile", "재검수", C.PROFILE_REVIEWED, reason.strip(), user_id)
    log_change(user_id, "review", "reopen", str(person_id), reason.strip())


def history(person_id: int) -> list[ReviewLog]:
    with session_scope() as s:
        return list(
            s.execute(
                select(ReviewLog).where(ReviewLog.person_id == person_id)
                .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
            ).scalars()
        )


def pending_people(limit: int = 500) -> list[tuple[int, str]]:
    with session_scope() as s:
        return list(
            s.execute(
                select(Person.person_id, Person.name_ko)
                .where(Person.profile_status == C.PROFILE_UNREVIEWED)
                .order_by(Person.person_id)
                .limit(limit)
            ).all()
        )


# ------------------------------------------------------------------ 충돌 알림 (F-08-4)

def open_alerts(person_id: int | None = None) -> list[ReviewQueue]:
    with session_scope() as s:
        rows = list(
            s.execute(
                select(ReviewQueue)
                .where(ReviewQueue.queue_type == C.QUEUE_CONFLICT, ReviewQueue.status == "대기")
                .order_by(ReviewQueue.created_at)
            ).scalars()
        )
    if person_id is None:
        return rows
    return [r for r in rows if (r.payload or {}).get("person_id") == person_id]


def resolve_alert(queue_id: int, user_id: int | None, accept_new: bool) -> None:
    """충돌 알림 처리. accept_new=True 면 자동 수집 값을 반영하고, 아니면 검수자 수정값을 유지한다."""
    with session_scope() as s:
        q = s.get(ReviewQueue, queue_id)
        if q is None or q.queue_type != C.QUEUE_CONFLICT or q.status != "대기":
            raise LookupError("처리할 수 있는 충돌 알림이 아닙니다.")
        p = q.payload or {}
        if accept_new:
            row = _get(s, p["person_id"], p["entity"], p["entity_id"])
            kind = EDITABLE[p["entity"]][p["field"]]
            setattr(row, p["field"], _convert(kind, p.get("new_value")))
        q.status = "반영" if accept_new else "유지"
        q.resolved_at = datetime.now(timezone.utc)
        q.resolved_by = user_id
        _log(s, p["person_id"], _path(p["entity"], p["entity_id"]), "충돌처리",
             f"{p['field']}={p.get('current_value')}", f"{p['field']}={p.get('new_value')} ({q.status})", user_id)
    log_change(user_id, "review", "conflict", str(queue_id), "반영" if accept_new else "유지")
