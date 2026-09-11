"""DB 접근 계층.

pages/ 는 절대 SQL 을 직접 쓰지 않고 이 모듈(또는 core/*)을 경유한다. (불변규칙 계층 규칙)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core import constants as C
from data.models import (
    AccessLog,
    Achievement,
    AppUser,
    Directorship,
    Expertise,
    Person,
    PersonIndustry,
    Pool,
    PoolMember,
    Position,
    Reputation,
    ScreeningResult,
    Source,
)
from data.session import session_scope


@dataclass
class PersonDetail:
    person: Person
    positions: list[Position] = field(default_factory=list)
    directorships: list[Directorship] = field(default_factory=list)
    expertises: list[Expertise] = field(default_factory=list)
    reputations: list[Reputation] = field(default_factory=list)
    achievements: list[Achievement] = field(default_factory=list)
    screenings: list[ScreeningResult] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    sources: dict[int, Source] = field(default_factory=dict)


def get_person_detail(person_id: int) -> PersonDetail | None:
    """상세 프로파일 1건. 출처는 id → Source 로 함께 반환한다 (PRD F-05-2)."""
    with session_scope() as s:
        person = s.execute(
            select(Person)
            .where(Person.person_id == person_id)
            .options(
                selectinload(Person.positions),
                selectinload(Person.directorships),
                selectinload(Person.expertises),
                selectinload(Person.reputations),
                selectinload(Person.achievements),
                selectinload(Person.screenings),
            )
        ).scalar_one_or_none()
        if person is None:
            return None

        industries = list(
            s.execute(
                select(PersonIndustry.industry_code).where(
                    PersonIndustry.person_id == person_id
                )
            ).scalars()
        )

        source_ids = set()
        for coll in (
            person.positions,
            person.directorships,
            person.expertises,
            person.reputations,
            person.achievements,
        ):
            source_ids.update(item.source_id for item in coll)
        sources = {}
        if source_ids:
            rows = s.execute(select(Source).where(Source.source_id.in_(source_ids))).scalars()
            sources = {src.source_id: src for src in rows}

        return PersonDetail(
            person=person,
            positions=list(person.positions),
            directorships=list(person.directorships),
            expertises=list(person.expertises),
            reputations=list(person.reputations),
            achievements=list(person.achievements),
            screenings=list(person.screenings),
            industries=industries,
            sources=sources,
        )


def get_persons(person_ids: list[int]) -> list[Person]:
    if not person_ids:
        return []
    with session_scope() as s:
        rows = s.execute(select(Person).where(Person.person_id.in_(person_ids))).scalars()
        return list(rows)


def list_person_options(limit: int = 1000) -> list[tuple[int, str]]:
    """후보 선택 드롭다운용 (id, 성명) 목록."""
    with session_scope() as s:
        rows = s.execute(
            select(Person.person_id, Person.name_ko).order_by(Person.person_id).limit(limit)
        ).all()
    return [(pid, name) for pid, name in rows]


def person_count() -> int:
    with session_scope() as s:
        return int(s.execute(select(func.count(Person.person_id))).scalar_one())


def unreviewed_count() -> int:
    with session_scope() as s:
        return int(
            s.execute(
                select(func.count(Person.person_id)).where(
                    Person.profile_status == C.PROFILE_UNREVIEWED
                )
            ).scalar_one()
        )


def screening_distribution() -> dict[str, int]:
    """대표 스크리닝 상태별 인원. 대시보드용."""
    with session_scope() as s:
        rows = s.execute(
            select(ScreeningResult.person_id, ScreeningResult.result)
        ).all()
    worst: dict[int, str] = {}
    for pid, result in rows:
        if result == C.SCREEN_INFO:  # 참고 정보는 대표 상태에 반영하지 않는다
            continue
        prev = worst.get(pid)
        if prev is None or C.SCREEN_ORDER[result] > C.SCREEN_ORDER[prev]:
            worst[pid] = result
    out = {C.SCREEN_PASS: 0, C.SCREEN_WARN: 0, C.SCREEN_FAIL: 0}
    total = person_count()
    for status in worst.values():
        out[status] += 1
    # 스크리닝 레코드가 없는 후보는 pass 로 본다
    out[C.SCREEN_PASS] += total - len(worst)
    return out


def expiring_directorships(months: int = 6) -> list[tuple[Person, Directorship, int]]:
    """잔여 임기가 임박한 건 (PRD F-03-1, 대시보드)."""
    with session_scope() as s:
        rows = s.execute(
            select(Person, Directorship)
            .join(Directorship, Directorship.person_id == Person.person_id)
            .where(
                Directorship.is_current.is_(True),
                Directorship.term_end_date.is_not(None),
            )
        ).all()
    out = []
    for person, d in rows:
        remaining = d.remaining_term_months()
        if remaining is not None and 0 <= remaining <= months:
            out.append((person, d, remaining))
    out.sort(key=lambda x: x[2])
    return out


def list_pools() -> list[Pool]:
    with session_scope() as s:
        return list(s.execute(select(Pool).order_by(Pool.created_at.desc())).scalars())


def pool_member_counts() -> dict[int, int]:
    with session_scope() as s:
        rows = s.execute(
            select(PoolMember.pool_id, func.count(PoolMember.id)).group_by(PoolMember.pool_id)
        ).all()
    return {pool_id: count for pool_id, count in rows}


def list_users() -> list[AppUser]:
    with session_scope() as s:
        return list(s.execute(select(AppUser).order_by(AppUser.user_id)).scalars())


def recent_access_logs(limit: int = 200) -> list[AccessLog]:
    with session_scope() as s:
        return list(
            s.execute(select(AccessLog).order_by(AccessLog.occurred_at.desc()).limit(limit)).scalars()
        )


def source_integrity_report() -> dict[str, int]:
    """출처 없는 사실 데이터가 있는지 점검 (PRD 인수기준 #5).

    스키마에서 NOT NULL 로 막고 있으므로 정상 상태에서는 전부 0 이어야 한다.
    """
    out = {}
    with session_scope() as s:
        for label, model in (
            ("경력", Position),
            ("타사등기임원", Directorship),
            ("전문분야", Expertise),
            ("평판", Reputation),
            ("업적", Achievement),
        ):
            out[label] = int(
                s.execute(
                    select(func.count()).select_from(model).where(model.source_id.is_(None))
                ).scalar_one()
            )
        # 근거 스니펫 공백인 전문분야 (불변규칙 2)
        out["근거없는 전문분야"] = int(
            s.execute(
                select(func.count())
                .select_from(Expertise)
                .where(
                    (Expertise.evidence_snippet.is_(None))
                    | (func.trim(Expertise.evidence_snippet) == "")
                )
            ).scalar_one()
        )
    return out
