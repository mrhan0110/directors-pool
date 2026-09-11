"""후보 검색 (PRD F-01, F-02).

핵심 규칙
- 최대 조회 인원 수는 '단순 절단'이 아니라 '정렬 기준 적용 후 상위 N명'이다.
  SQL LIMIT 으로 DB 단에서 제한하고, 전체 매칭 건수는 별도 COUNT 로 구한다. (F-01-8, F-09-5-1)
- 미선택 필터는 조건에서 제외한다. (F-01-1)
- 결격(fail) 후보는 정렬 결과와 무관하게 하단으로 분리한다. (F-06)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import Select, case, exists, func, or_, select

from core import constants as C
from core import codes as CODES
from core import scoring
from core import settings
from data.models import (
    Directorship,
    Expertise,
    Person,
    PersonIndustry,
    Position,
    Reputation,
    ScreeningResult,
)
from data.session import session_scope


@dataclass
class SearchRow:
    person_id: int
    name_ko: str
    gender: str | None
    age: int | None
    age_estimated: bool
    current_org: str | None
    current_title: str | None
    concurrent_count: int
    screening: str
    updated_at: datetime
    expertise_labels: list[str] = field(default_factory=list)
    directorship_summary: str = ""
    fit_score: float | None = None  # None = 미산출 (PRD F-06)
    fit_basis: str = ""             # 점수 근거 요약 (PRD §6.2)


@dataclass
class SearchResult:
    rows: list[SearchRow]
    total_matched: int          # 조건에 맞는 전체 인원 (절단 전)
    shown: int                  # 실제 표시 인원
    effective_limit: int        # 적용된 상한
    limit_capped_by: str | None  # 'system' | 'viewer' | None
    sort_code: str


# ------------------------------------------------------------------ 상한 계산

def resolve_limit(limit_code: str | None, role: str | None) -> tuple[int, str | None]:
    """드롭다운 선택값 → 실제 LIMIT.

    '전체'를 골라도 시스템 상한을 넘지 못한다. 외부뷰어는 별도 상한을 적용한다. (F-01-8)
    반환: (적용 상한, 상한을 건 주체)
    """
    system_max = settings.get_int(C.SET_RESULT_LIMIT_SYSTEM_MAX)
    requested: int | None
    if limit_code is None:
        requested = settings.get_int(C.SET_RESULT_LIMIT_DEFAULT)
    else:
        requested = CODES.extra_of(C.CODE_RESULT_LIMIT, limit_code).get("value")

    capped_by: str | None = None
    limit = system_max if requested is None else requested
    if requested is None or requested > system_max:
        limit = system_max
        capped_by = "system"

    if role == C.ROLE_VIEWER:
        viewer_max = settings.get_int(C.SET_RESULT_LIMIT_VIEWER_MAX)
        if limit > viewer_max:
            limit = viewer_max
            capped_by = "viewer"
    return limit, capped_by


# ------------------------------------------------------------------ 파생 컬럼

def _concurrent_count_sq():
    return (
        select(func.count(Directorship.directorship_id))
        .where(
            Directorship.person_id == Person.person_id,
            Directorship.is_current.is_(True),
        )
        .correlate(Person)
        .scalar_subquery()
    )


def _screening_case():
    """룰 판정 중 가장 나쁜 결과를 후보의 스크리닝 상태로 본다.

    법무 수기 판정(reviewer_override)이 있으면 자동 판정보다 우선한다. info 는 pass 취급.
    """
    effective = func.coalesce(ScreeningResult.reviewer_override, ScreeningResult.result)
    has_fail = exists().where(
        ScreeningResult.person_id == Person.person_id,
        effective == C.SCREEN_FAIL,
    )
    has_warn = exists().where(
        ScreeningResult.person_id == Person.person_id,
        effective == C.SCREEN_WARN,
    )
    return case((has_fail, C.SCREEN_FAIL), (has_warn, C.SCREEN_WARN), else_=C.SCREEN_PASS)


# ------------------------------------------------------------------ 필터 적용

def _apply_filters(stmt: Select, f: dict[str, Any], today: date | None = None) -> Select:
    today = today or date.today()

    if f.get("gender"):
        stmt = stmt.where(Person.gender == f["gender"])

    # 연령대: 출생연도로 환산해 질의한다
    bands = f.get("age_bands") or []
    if bands:
        clauses = []
        for code in bands:
            extra = CODES.extra_of(C.CODE_AGE_BAND, code)
            lo, hi = extra.get("min"), extra.get("max")
            cond = []
            if hi is not None:
                cond.append(Person.birth_year >= today.year - hi)
            if lo is not None:
                cond.append(Person.birth_year <= today.year - lo)
            if cond:
                from sqlalchemy import and_

                clauses.append(and_(*cond))
        if clauses:
            stmt = stmt.where(or_(*clauses))

    if f.get("nationalities"):
        stmt = stmt.where(Person.nationality_primary.in_(f["nationalities"]))

    if f.get("regions"):
        stmt = stmt.where(Person.residence_region.in_(f["regions"]))

    # 직업: 현직/전직 범위에 따라 Position 을 좁힌다
    job_l1 = f.get("job_l1") or []
    job_l2 = f.get("job_l2") or []
    role_levels = f.get("role_levels") or []
    scope = f.get("job_scope") or "BOTH"
    if job_l1 or job_l2 or role_levels:
        conds = [Position.person_id == Person.person_id]
        if scope == "CURRENT":
            conds.append(Position.is_current.is_(True))
        elif scope == "PAST":
            conds.append(Position.is_current.is_(False))
        if job_l2:
            conds.append(Position.job_l2_code.in_(job_l2))
        elif job_l1:
            conds.append(Position.job_l1_code.in_(job_l1))
        if role_levels:
            conds.append(Position.role_level.in_(role_levels))
        stmt = stmt.where(exists().where(*conds))

    # 전문분야: 중분류가 선택되면 중분류 우선, 아니면 대분류 접두어로 매칭
    exp_l2 = f.get("expertise_l2") or []
    exp_l1 = f.get("expertise_l1") or []
    if exp_l2:
        stmt = stmt.where(
            exists().where(
                Expertise.person_id == Person.person_id,
                Expertise.taxonomy_code.in_(exp_l2),
            )
        )
    elif exp_l1:
        likes = [Expertise.taxonomy_code.like(f"{code}%") for code in exp_l1]
        stmt = stmt.where(
            exists().where(Expertise.person_id == Person.person_id, or_(*likes))
        )

    if f.get("industries"):
        stmt = stmt.where(
            exists().where(
                PersonIndustry.person_id == Person.person_id,
                PersonIndustry.industry_code.in_(f["industries"]),
            )
        )

    # 현 타사 등기임원 겸직 수
    if f.get("concurrent"):
        extra = CODES.extra_of(C.CODE_CONCURRENT, f["concurrent"])
        cnt = _concurrent_count_sq()
        if extra.get("min") is not None:
            stmt = stmt.where(cnt >= extra["min"])
        if extra.get("max") is not None:
            stmt = stmt.where(cnt <= extra["max"])

    # 겸직 잔여임기: 현재 진행 중인 등기임원 건의 임기만료일 기준
    if f.get("term_remain"):
        extra = CODES.extra_of(C.CODE_TERM_REMAIN, f["term_remain"])
        conds = [
            Directorship.person_id == Person.person_id,
            Directorship.is_current.is_(True),
            Directorship.term_end_date.is_not(None),
        ]
        if extra.get("max_months") is not None:
            conds.append(
                Directorship.term_end_date <= today + timedelta(days=30 * extra["max_months"])
            )
            conds.append(Directorship.term_end_date >= today)
        if extra.get("min_months") is not None:
            conds.append(
                Directorship.term_end_date > today + timedelta(days=30 * extra["min_months"])
            )
        stmt = stmt.where(exists().where(*conds))

    # 스크리닝
    if f.get("screening"):
        allow = CODES.extra_of(C.CODE_SCREENING, f["screening"]).get("allow", [])
        if allow:
            stmt = stmt.where(_screening_case().in_(allow))

    # 확인된 부정 이슈 제외 (미확인 건은 제외 조건에 넣지 않는다 — PRD F-03 (5))
    if f.get("reputation"):
        extra = CODES.extra_of(C.CODE_REPUTATION, f["reputation"])
        if extra.get("exclude_verified_negative"):
            stmt = stmt.where(
                ~exists().where(
                    Reputation.person_id == Person.person_id,
                    Reputation.polarity == "부정",
                    Reputation.verified_yn.is_(True),
                )
            )

    if f.get("freshness"):
        months = CODES.extra_of(C.CODE_FRESHNESS, f["freshness"]).get("months")
        if months:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
            stmt = stmt.where(Person.updated_at >= cutoff)

    return stmt


def _apply_sort(stmt: Select, sort_code: str | None, fit=None) -> Select:
    """결격 후보만 항상 하단으로 분리하고, 그 안에서 선택한 정렬을 적용한다 (PRD F-06).

    확인 필요(🟡)는 분리하지 않는다 — 리스크는 이미 적합도 감점에 반영되어 있다.
    마지막에 person_id 를 붙여 정렬을 안정적으로 만든다(페이지 간 중복·누락 방지).
    """
    fail_rank = case((_screening_case() == C.SCREEN_FAIL, 1), else_=0)
    stmt = stmt.order_by(fail_rank)

    if sort_code == "FEWEST":
        return stmt.order_by(_concurrent_count_sq().asc(), Person.person_id)
    if sort_code == "AGE_ASC":
        return stmt.order_by(Person.birth_year.desc().nulls_last(), Person.person_id)
    if sort_code == "FRESH":
        return stmt.order_by(Person.updated_at.desc(), Person.person_id)
    # FIT: 기본 점수(PersonScore) + 전문분야 매칭도(검색 조건 기준)
    fit = fit if fit is not None else scoring.fit_expr({})
    return stmt.order_by(fit.desc(), Person.person_id)


# ------------------------------------------------------------------ 실행

def count_matches(f: dict[str, Any]) -> int:
    stmt = _apply_filters(select(func.count(Person.person_id)), f)
    with session_scope() as s:
        return int(s.execute(stmt).scalar_one())


def search(
    f: dict[str, Any],
    limit_code: str | None,
    role: str | None,
    offset: int = 0,
) -> SearchResult:
    limit, capped_by = resolve_limit(limit_code, role)
    total = count_matches(f)
    sort_code = f.get("sort") or "FIT"
    fit = scoring.fit_expr(f)

    stmt = select(
        Person.person_id,
        Person.name_ko,
        Person.gender,
        Person.birth_year,
        Person.age_estimated_yn,
        Person.updated_at,
        _concurrent_count_sq().label("concurrent_count"),
        _screening_case().label("screening"),
        fit.label("fit_score"),
    )
    stmt = _apply_filters(stmt, f)
    stmt = _apply_sort(stmt, sort_code, fit)
    stmt = stmt.limit(limit).offset(offset)

    today = date.today()
    with session_scope() as s:
        records = s.execute(stmt).all()
        ids = [r.person_id for r in records]

        current_pos = _current_positions(s, ids)
        exp_labels = _expertise_labels(s, ids)
        dir_summary = _directorship_summary(s, ids)
        scores = scoring.breakdowns_in(s, ids)

    def _fit(r) -> tuple[float | None, str]:
        sc = scores.get(r.person_id)
        if sc is None:
            return None, ""
        value = float(r.fit_score or 0.0)
        return round(value, 1), scoring.describe(sc["breakdown"], value - sc["base"])

    rows = [
        SearchRow(
            person_id=r.person_id,
            name_ko=r.name_ko,
            gender=r.gender,
            age=(today.year - r.birth_year) if r.birth_year else None,
            age_estimated=bool(r.age_estimated_yn),
            current_org=current_pos.get(r.person_id, (None, None))[0],
            current_title=current_pos.get(r.person_id, (None, None))[1],
            concurrent_count=int(r.concurrent_count or 0),
            screening=r.screening,
            updated_at=r.updated_at,
            expertise_labels=exp_labels.get(r.person_id, []),
            directorship_summary=dir_summary.get(r.person_id, "없음"),
            fit_score=_fit(r)[0],
            fit_basis=_fit(r)[1],
        )
        for r in records
    ]

    return SearchResult(
        rows=rows,
        total_matched=total,
        shown=len(rows),
        effective_limit=limit,
        limit_capped_by=capped_by,
        sort_code=sort_code,
    )


def _current_positions(s, ids: Sequence[int]) -> dict[int, tuple[str, str]]:
    if not ids:
        return {}
    stmt = (
        select(Position.person_id, Position.org_name, Position.title, Position.start_date)
        .where(Position.person_id.in_(ids), Position.is_current.is_(True))
        .order_by(Position.person_id, Position.start_date.desc())
    )
    out: dict[int, tuple[str, str]] = {}
    for pid, org, title, _ in s.execute(stmt).all():
        out.setdefault(pid, (org, title))
    return out


def _expertise_labels(s, ids: Sequence[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    stmt = (
        select(Expertise.person_id, Expertise.taxonomy_code)
        .where(
            Expertise.person_id.in_(ids),
            Expertise.is_primary.is_(True),
            # 근거 스니펫 없는 전문분야는 목록에도 내보내지 않는다 (불변규칙 2)
            func.trim(Expertise.evidence_snippet) != "",
        )
        .order_by(Expertise.person_id, Expertise.score.desc())
    )
    labels_l1 = CODES.code_map(C.CODE_EXPERTISE_L1)
    labels_l2 = CODES.code_map(C.CODE_EXPERTISE_L2)
    out: dict[int, list[str]] = {}
    for pid, code in s.execute(stmt).all():
        label = labels_l2.get(code) or labels_l1.get(code) or code
        out.setdefault(pid, [])
        if len(out[pid]) < 3:  # 대표 전문분야는 최대 3개 (PRD F-04)
            out[pid].append(label)
    return out


def _directorship_summary(s, ids: Sequence[int]) -> dict[int, str]:
    if not ids:
        return {}
    stmt = (
        select(Directorship.person_id, Directorship.company_name)
        .where(Directorship.person_id.in_(ids), Directorship.is_current.is_(True))
        .order_by(Directorship.person_id)
    )
    acc: dict[int, list[str]] = {}
    for pid, company in s.execute(stmt).all():
        acc.setdefault(pid, []).append(company)
    out = {}
    for pid in ids:
        names = acc.get(pid, [])
        if not names:
            out[pid] = "없음"
        elif len(names) <= 2:
            out[pid] = ", ".join(names)
        else:
            out[pid] = f"{names[0]} 외 {len(names) - 1}곳"
    return out


# ------------------------------------------------------------------ 조건 완화 제안 (F-01-6)

_RELAXABLE = [
    ("age_bands", "연령"),
    ("expertise_l2", "전문분야(중분류)"),
    ("expertise_l1", "전문분야(대분류)"),
    ("job_l2", "직업(중분류)"),
    ("job_l1", "직업(대분류)"),
    ("industries", "산업 도메인"),
    ("concurrent", "겸직 수"),
    ("term_remain", "겸직 잔여임기"),
    ("regions", "지역"),
    ("nationalities", "국적"),
    ("gender", "성별"),
    ("screening", "스크리닝"),
    ("freshness", "데이터 최신성"),
]


def relaxation_suggestions(f: dict[str, Any], top_n: int = 3) -> list[tuple[str, int]]:
    """어떤 필터를 빼면 몇 명이 되는지 계산한다 (PRD F-01-6)."""
    suggestions: list[tuple[str, int]] = []
    for key, label in _RELAXABLE:
        value = f.get(key)
        if not value:
            continue
        relaxed = dict(f)
        relaxed[key] = [] if isinstance(value, list) else None
        n = count_matches(relaxed)
        if n > 0:
            suggestions.append((label, n))
    suggestions.sort(key=lambda x: -x[1])
    return suggestions[:top_n]


def option_counts(f: dict[str, Any], category: str, filter_key: str) -> dict[str, int]:
    """드롭다운 항목별 후보 건수 배지 (PRD F-01-3).

    해당 필터만 각 값으로 바꿔가며 센다(그 필터를 제외한 나머지 조건 기준).
    """
    out: dict[str, int] = {}
    for item in CODES.load_codes(category):
        probe = dict(f)
        probe[filter_key] = [item.code] if isinstance(f.get(filter_key), list) else item.code
        out[item.code] = count_matches(probe)
    return out
