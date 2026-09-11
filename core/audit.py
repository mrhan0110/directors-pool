"""접근 로그 기록 (PRD F-09-22).

Streamlit 기본 로그로는 '누가 어떤 후보를 열람했는가'를 남길 수 없으므로
애플리케이션 레벨에서 DB 에 적재한다.
"""

from __future__ import annotations

from sqlalchemy import select

from core import constants as C
from data.models import AccessLog, AuditLog
from data.session import session_scope


def log_access(
    user_id: int | None,
    action: str,
    page: str | None = None,
    target_person_ids: list[int] | None = None,
    detail: str | None = None,
    share_id: int | None = None,
) -> None:
    """로그 적재 실패가 화면 동작을 막지 않도록 예외를 삼킨다.

    단, 조용히 사라지면 감사 공백이 생기므로 stderr 로는 남긴다.
    """
    try:
        with session_scope() as s:
            s.add(
                AccessLog(
                    user_id=user_id,
                    share_id=share_id,
                    page=page,
                    action=action,
                    target_person_ids=target_person_ids or [],
                    detail=detail,
                )
            )
    except Exception as exc:  # pragma: no cover
        import sys

        print(f"[audit] AccessLog 적재 실패: {exc}", file=sys.stderr)


def log_change(
    user_id: int | None,
    entity: str,
    action: str,
    entity_id: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        with session_scope() as s:
            s.add(
                AuditLog(
                    user_id=user_id,
                    entity=entity,
                    entity_id=entity_id,
                    action=action,
                    detail=detail,
                )
            )
    except Exception as exc:  # pragma: no cover
        import sys

        print(f"[audit] AuditLog 적재 실패: {exc}", file=sys.stderr)


def log_denied(user_id: int | None, page: str, role: str | None) -> None:
    log_access(user_id, C.ACT_DENIED, page=page, detail=f"role={role}")


def history_of(entity: str, prefix: str | None = None, limit: int = 200) -> list[AuditLog]:
    """관리자 화면의 변경 이력 조회(코드·설정 등). 최신순."""
    stmt = select(AuditLog).where(AuditLog.entity == entity)
    if prefix:
        stmt = stmt.where(AuditLog.entity_id.like(f"{prefix}%"))
    stmt = stmt.order_by(AuditLog.occurred_at.desc()).limit(limit)
    with session_scope() as s:
        return list(s.execute(stmt).scalars())
