"""POOL 관리 (PRD F-07, F-02-2).

- 상태 전이: 후보 등록 → 1차 검토 → 법무 검증 → 사추위 보고 → 접촉 → 최종후보 / 보류 / 제외
- 보류·제외는 사유 필수. 모든 변경은 PoolEvent 타임라인과 AuditLog 에 남는다.
- 동시 수정: 상태 변경은 호출자가 본 이전 상태(expected_state)를 함께 받아, 그 사이 다른 사람이
  바꿨으면 거부한다(마지막 저장이 조용히 이기는 것을 막는다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select

from core import constants as C
from core.audit import log_change
from data.models import Person, Pool, PoolEvent, PoolMember, ShareLink
from data.session import session_scope

FLOW = C.POOL_MEMBER_STATES[:6]          # 정상 진행 단계
HOLD, EXCLUDED = "보류", "제외"
REASON_REQUIRED = C.POOL_MEMBER_STATES_REQUIRING_REASON


class ConcurrentUpdateError(RuntimeError):
    """다른 사용자가 먼저 상태를 바꿨다."""


@dataclass(frozen=True)
class MemberView:
    person_id: int
    name_ko: str
    state: str
    reason: str | None
    note: str | None
    added_at: datetime
    profile_status: str


def allowed_transitions(current: str) -> list[str]:
    """현재 상태에서 갈 수 있는 상태. 정상 흐름은 한 단계씩(앞/뒤), 보류·제외는 어디서나."""
    out: list[str] = []
    if current in FLOW:
        i = FLOW.index(current)
        if i + 1 < len(FLOW):
            out.append(FLOW[i + 1])
        if i > 0:
            out.append(FLOW[i - 1])
        out += [HOLD, EXCLUDED]
    elif current == HOLD:
        out += list(FLOW) + [EXCLUDED]
    elif current == EXCLUDED:
        out.append(FLOW[0])  # 재등록
    return out


# ------------------------------------------------------------------ POOL CRUD

def create_pool(
    name: str,
    user_id: int | None,
    purpose: str | None = None,
    target_position: str | None = None,
    target_count: int | None = None,
    deadline: date | None = None,
    memo: str | None = None,
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("POOL 명칭을 입력하세요.")
    with session_scope() as s:
        pool = Pool(
            name=name,
            purpose=(purpose or "").strip() or None,
            target_position=(target_position or "").strip() or None,
            target_count=target_count,
            deadline=deadline,
            created_by=user_id,
        )
        s.add(pool)
        s.flush()
        if memo and memo.strip():
            s.add(PoolEvent(pool_id=pool.pool_id, event="코멘트", comment=memo.strip(), user_id=user_id))
        pool_id = pool.pool_id
    log_change(user_id, "pool", "create", str(pool_id), name)
    return pool_id


def update_pool(pool_id: int, user_id: int | None, **fields) -> None:
    editable = {"name", "purpose", "target_position", "target_count", "deadline"}
    unknown = set(fields) - editable
    if unknown:
        raise ValueError(f"수정할 수 없는 항목입니다: {unknown}")
    if "name" in fields and not (fields["name"] or "").strip():
        raise ValueError("POOL 명칭을 입력하세요.")
    with session_scope() as s:
        pool = s.get(Pool, pool_id)
        if pool is None:
            raise LookupError(f"POOL 이 없습니다: {pool_id}")
        for k, v in fields.items():
            setattr(pool, k, v.strip() if isinstance(v, str) else v)
    log_change(user_id, "pool", "update", str(pool_id), ", ".join(sorted(fields)))


def delete_pool(pool_id: int, user_id: int | None) -> None:
    """공유 이력이 있는 POOL 은 삭제하지 않는다 — 공유·접속 이력이 감사 대상이기 때문."""
    with session_scope() as s:
        pool = s.get(Pool, pool_id)
        if pool is None:
            raise LookupError(f"POOL 이 없습니다: {pool_id}")
        shared = s.execute(
            select(func.count(ShareLink.share_id)).where(ShareLink.pool_id == pool_id)
        ).scalar_one()
        if shared:
            raise ValueError("공유 링크 발급 이력이 있는 POOL 은 삭제할 수 없습니다. 링크를 회수하고 보관하세요.")
        for ev in s.execute(select(PoolEvent).where(PoolEvent.pool_id == pool_id)).scalars():
            s.delete(ev)
        s.delete(pool)
    log_change(user_id, "pool", "delete", str(pool_id))


def get_pool(pool_id: int) -> Pool | None:
    with session_scope() as s:
        return s.get(Pool, pool_id)


def list_pools(pool_ids: list[int] | None = None) -> list[Pool]:
    """pool_ids 를 주면 그 POOL 만 (외부뷰어 범위 제한용)."""
    with session_scope() as s:
        stmt = select(Pool).order_by(Pool.created_at.desc(), Pool.pool_id.desc())
        if pool_ids is not None:
            stmt = stmt.where(Pool.pool_id.in_(pool_ids))
        return list(s.execute(stmt).scalars())


# ------------------------------------------------------------------ 구성원

def add_members(pool_id: int, person_ids: list[int], user_id: int | None, note: str | None = None) -> tuple[int, int]:
    """(추가 수, 이미 있어 건너뛴 수)."""
    added = skipped = 0
    with session_scope() as s:
        if s.get(Pool, pool_id) is None:
            raise LookupError(f"POOL 이 없습니다: {pool_id}")
        existing = set(
            s.execute(select(PoolMember.person_id).where(PoolMember.pool_id == pool_id)).scalars()
        )
        for pid in dict.fromkeys(person_ids):
            if pid in existing:
                skipped += 1
                continue
            s.add(PoolMember(pool_id=pool_id, person_id=pid, state=FLOW[0], note=note, added_by=user_id))
            s.add(PoolEvent(pool_id=pool_id, person_id=pid, event="추가", to_state=FLOW[0],
                            comment=note, user_id=user_id))
            added += 1
    if added:
        log_change(user_id, "pool_member", "add", str(pool_id), f"{added}명")
    return added, skipped


def change_state(
    pool_id: int,
    person_id: int,
    to_state: str,
    user_id: int | None,
    reason: str | None = None,
    expected_state: str | None = None,
) -> None:
    if to_state in REASON_REQUIRED and not (reason and reason.strip()):
        raise ValueError(f"'{to_state}' 처리에는 사유 입력이 필수입니다. (PRD F-07)")
    with session_scope() as s:
        m = s.execute(
            select(PoolMember).where(PoolMember.pool_id == pool_id, PoolMember.person_id == person_id)
        ).scalar_one_or_none()
        if m is None:
            raise LookupError("POOL 에 등록되지 않은 후보입니다.")
        if expected_state is not None and m.state != expected_state:
            raise ConcurrentUpdateError(
                f"다른 사용자가 먼저 상태를 '{m.state}'(으)로 변경했습니다. 화면을 새로고침하세요."
            )
        if to_state not in allowed_transitions(m.state):
            raise ValueError(f"'{m.state}'에서 '{to_state}'(으)로 바로 변경할 수 없습니다.")
        before = m.state
        m.state = to_state
        m.reason = reason.strip() if reason and reason.strip() else (None if to_state in FLOW else m.reason)
        s.add(PoolEvent(pool_id=pool_id, person_id=person_id, event="상태변경", from_state=before,
                        to_state=to_state, comment=(reason or "").strip() or None, user_id=user_id))
    log_change(user_id, "pool_member", "state", f"{pool_id}/{person_id}", f"{before}→{to_state}")


def add_comment(pool_id: int, comment: str, user_id: int | None, person_id: int | None = None) -> None:
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("코멘트를 입력하세요.")
    with session_scope() as s:
        s.add(PoolEvent(pool_id=pool_id, person_id=person_id, event="코멘트", comment=comment, user_id=user_id))


def members(pool_id: int) -> list[MemberView]:
    with session_scope() as s:
        rows = s.execute(
            select(PoolMember, Person.name_ko, Person.profile_status)
            .join(Person, Person.person_id == PoolMember.person_id)
            .where(PoolMember.pool_id == pool_id)
            .order_by(PoolMember.added_at, PoolMember.id)
        ).all()
    return [
        MemberView(m.person_id, name, m.state, m.reason, m.note, m.added_at, status)
        for m, name, status in rows
    ]


def member_ids(pool_ids: list[int]) -> set[int]:
    if not pool_ids:
        return set()
    with session_scope() as s:
        return set(
            s.execute(select(PoolMember.person_id).where(PoolMember.pool_id.in_(pool_ids))).scalars()
        )


def timeline(pool_id: int) -> list[PoolEvent]:
    with session_scope() as s:
        return list(
            s.execute(
                select(PoolEvent)
                .where(PoolEvent.pool_id == pool_id)
                .order_by(PoolEvent.occurred_at.desc(), PoolEvent.id.desc())
            ).scalars()
        )


def member_counts() -> dict[int, int]:
    with session_scope() as s:
        rows = s.execute(
            select(PoolMember.pool_id, func.count(PoolMember.id)).group_by(PoolMember.pool_id)
        ).all()
    return {pid: n for pid, n in rows}
