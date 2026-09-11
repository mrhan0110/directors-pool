"""결격·리스크 스크리닝 룰 엔진 (PRD §5.1, R-01~R-08).

설계 원칙
- 임계값과 판정 기준 목록은 전부 AppSetting 에서 읽는다(OrgContext.load). 이 모듈에 숫자를 쓰지 않는다. (불변규칙 4)
- 판정 결과에는 반드시 사유와 근거 데이터를 남긴다.
- 사람의 자격을 부정하는 판정이므로, 근거가 불충분하면 fail 이 아니라 warn 으로 둔다.
- 미확인 평판은 판정에 반영하지 않는다 (PRD F-03 (5)).
- 법무가 입력한 수기 판정(reviewer_override)은 재평가해도 보존하며 자동 판정보다 우선한다.
- 룰 판정은 1차 스크리닝(참고)이며 최종 적격성은 법무 검토로 확정한다 (PRD §4.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import func, select

from core import constants as C
from core import settings
from data.models import Person, ScreeningResult
from data.session import session_scope


@dataclass(frozen=True)
class RuleVerdict:
    rule_id: str
    result: str  # pass / warn / fail / info
    reason: str | None = None


@dataclass(frozen=True)
class OrgContext:
    """판정 기준. 전부 관리자 화면(AppSetting)에서 관리한다."""

    own_company: str
    affiliates: tuple[str, ...]
    major_shareholders: tuple[str, ...]
    conflict_orgs: tuple[str, ...]
    cooling_off_years: int
    concurrent_limit: int
    tenure_limit_years: int
    affiliate_tenure_limit_years: int
    total_assets_krw: int
    gender_rule_asset_threshold_krw: int
    board_female_count: int
    r06_fail_categories: tuple[str, ...]
    audit_expert_certs: tuple[str, ...]
    audit_expert_jobs: tuple[str, ...]
    audit_expert_expertise: tuple[str, ...]

    @classmethod
    def load(cls) -> "OrgContext":
        return cls(
            own_company=settings.get_str(C.SET_OWN_COMPANY),
            affiliates=tuple(settings.get_list(C.SET_AFFILIATES)),
            major_shareholders=tuple(settings.get_list(C.SET_MAJOR_SHAREHOLDERS)),
            conflict_orgs=tuple(settings.get_list(C.SET_CONFLICT_ORGS)),
            cooling_off_years=settings.get_int(C.SET_COOLING_OFF_YEARS),
            concurrent_limit=settings.get_int(C.SET_CONCURRENT_LIMIT),
            tenure_limit_years=settings.get_int(C.SET_TENURE_LIMIT_YEARS),
            affiliate_tenure_limit_years=settings.get_int(C.SET_AFFILIATE_TENURE_LIMIT_YEARS),
            total_assets_krw=settings.get_int(C.SET_TOTAL_ASSETS_KRW),
            gender_rule_asset_threshold_krw=settings.get_int(C.SET_GENDER_RULE_ASSET_THRESHOLD),
            board_female_count=settings.get_int(C.SET_BOARD_FEMALE_COUNT),
            r06_fail_categories=tuple(settings.get_list(C.SET_R06_FAIL_CATEGORIES)),
            audit_expert_certs=tuple(settings.get_list(C.SET_AUDIT_EXPERT_CERTS)),
            audit_expert_jobs=tuple(settings.get_list(C.SET_AUDIT_EXPERT_JOBS)),
            audit_expert_expertise=tuple(settings.get_list(C.SET_AUDIT_EXPERT_EXPERTISE)),
        )


@dataclass
class ScreeningInput:
    """판정에 필요한 후보 데이터. DB 없이 단위테스트할 수 있도록 분리한다."""

    gender: str | None = None
    certifications: list[str] = field(default_factory=list)
    positions: list[Any] = field(default_factory=list)
    directorships: list[Any] = field(default_factory=list)
    reputations: list[Any] = field(default_factory=list)
    expertise_codes: list[str] = field(default_factory=list)

    @classmethod
    def from_detail(cls, detail) -> "ScreeningInput":
        return cls(
            gender=detail.person.gender,
            certifications=list(detail.person.certifications or []),
            positions=list(detail.positions),
            directorships=list(detail.directorships),
            reputations=list(detail.reputations),
            expertise_codes=[e.taxonomy_code for e in detail.expertises],
        )


# ------------------------------------------------------------------ 공통 도구

def _norm(name: str | None) -> str:
    s = (name or "").replace("(주)", "").replace("주식회사", "").replace(" ", "")
    return s.lower()


def _matches_any(org: str | None, names: Iterable[str]) -> str | None:
    """기관명이 목록 중 하나와 일치하거나 그 이름을 포함하면 해당 이름을 반환."""
    o = _norm(org)
    if not o:
        return None
    for n in names:
        nn = _norm(n)
        if nn and (o == nn or nn in o):
            return n
    return None


def years_ago(today: date, years: int) -> date:
    """N년 전 같은 날. 2월 29일은 28일로 보정한다."""
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


@dataclass(frozen=True)
class _Stint:
    """재직 1건 (경력·등기임원 공통 표현)."""

    org: str
    title: str
    start: date | None
    end: date | None
    is_current: bool
    is_full_time: bool

    @property
    def label(self) -> str:
        return f"{self.org} {self.title}".strip()


def _stints(data: ScreeningInput) -> list[_Stint]:
    out = [
        _Stint(
            org=p.org_name,
            title=p.title,
            start=p.start_date,
            end=None if p.is_current else p.end_date,
            is_current=bool(p.is_current),
            is_full_time=bool(p.is_full_time),
        )
        for p in data.positions
    ]
    out += [
        _Stint(
            org=d.company_name,
            title=d.role_type,
            start=d.appointed_date,
            end=None if d.is_current else d.term_end_date,
            is_current=bool(d.is_current),
            is_full_time=False,
        )
        for d in data.directorships
    ]
    return out


def _years(stint: _Stint, today: date) -> float:
    end = stint.end or today
    return max(0.0, (end - stint.start).days / 365.25) if stint.start else 0.0


def _verdict(rule_id: str, fails: list[str], warns: list[str], ok_reason: str) -> RuleVerdict:
    if fails:
        return RuleVerdict(rule_id, C.SCREEN_FAIL, " / ".join(fails + warns))
    if warns:
        return RuleVerdict(rule_id, C.SCREEN_WARN, " / ".join(warns))
    return RuleVerdict(rule_id, C.SCREEN_PASS, ok_reason)


# ------------------------------------------------------------------ 룰

def rule_r01(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """자사·계열사 상근 임직원 또는 냉각기간 내 재직 이력."""
    targets = (ctx.own_company, *ctx.affiliates)
    cutoff = years_ago(today, ctx.cooling_off_years)
    fails: list[str] = []
    warns: list[str] = []
    for s in _stints(data):
        if not _matches_any(s.org, targets):
            continue
        if s.is_current:
            if s.is_full_time:
                fails.append(f"자사·계열사 현직 상근: {s.label}")
            else:
                warns.append(f"자사·계열사 현직 비상근 — 관계 확인 필요: {s.label}")
        elif s.end is None:
            warns.append(f"자사·계열사 재직 종료일 미상: {s.label}")
        elif s.end >= cutoff:
            fails.append(
                f"냉각기간 {ctx.cooling_off_years}년 내 자사·계열사 재직: {s.label} (종료 {s.end.isoformat()})"
            )
    return _verdict("R-01", fails, warns, "자사·계열사 재직 이력 없음")


def rule_r02(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """최대주주·주요주주 및 특수관계인 여부."""
    cutoff = years_ago(today, ctx.cooling_off_years)
    fails: list[str] = []
    warns: list[str] = []
    for s in _stints(data):
        if not _matches_any(s.org, ctx.major_shareholders):
            continue
        if s.is_current:
            fails.append(f"최대주주·특수관계 기관 현직: {s.label}")
        elif s.end is None:
            warns.append(f"최대주주·특수관계 기관 재직 종료일 미상: {s.label}")
        elif s.end >= cutoff:
            warns.append(f"최대주주·특수관계 기관 최근 재직: {s.label} (종료 {s.end.isoformat()})")
    return _verdict("R-02", fails, warns, "최대주주·특수관계 기관 관련 이력 없음")


def rule_r03(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """주요 거래처·자문사 등 이해상충. 자동으로는 fail 을 내지 않는다(확인 필요)."""
    cutoff = years_ago(today, ctx.cooling_off_years)
    warns: list[str] = []
    for s in _stints(data):
        if not _matches_any(s.org, ctx.conflict_orgs):
            continue
        if s.is_current:
            warns.append(f"이해상충 기관 현직: {s.label}")
        elif s.end is None or s.end >= cutoff:
            ended = s.end.isoformat() if s.end else "종료일 미상"
            warns.append(f"이해상충 기관 최근 재직: {s.label} ({ended})")
    return _verdict("R-03", [], warns, "등록된 이해상충 기관 관련 이력 없음")


def rule_r04(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """타사 상장사 겸직 수 한도. 한도 초과 fail, 한도 도달 warn(자사 선임 시 초과 우려)."""
    own = (ctx.own_company, *ctx.affiliates)
    listed = [
        d.company_name
        for d in data.directorships
        if d.is_current and d.listed_yn and not _matches_any(d.company_name, own)
    ]
    n, limit = len(listed), ctx.concurrent_limit
    detail = f"현 타사 상장사 등기임원 {n}건({', '.join(listed) or '없음'}), 설정 한도 {limit}건"
    if n > limit:
        return RuleVerdict("R-04", C.SCREEN_FAIL, f"겸직 한도 초과 — {detail}")
    if n == limit and n > 0:
        return RuleVerdict("R-04", C.SCREEN_WARN, f"겸직 한도 도달 — {detail}")
    return RuleVerdict("R-04", C.SCREEN_PASS, detail)


def rule_r05(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """자사 재직 연수 상한(연속) 및 계열 합산 상한."""
    own_years = 0.0
    group_years = 0.0
    warns: list[str] = []
    for s in _stints(data):
        aff = _matches_any(s.org, ctx.affiliates)
        own = None if aff else _matches_any(s.org, (ctx.own_company,))
        if not (aff or own):
            continue
        if s.start is None:
            warns.append(f"재직 시작일 미상으로 연수 산정 불가: {s.label}")
            continue
        y = _years(s, today)
        group_years += y
        if own:
            own_years += y
    fails: list[str] = []
    if own_years > ctx.tenure_limit_years:
        fails.append(f"자사 재직 {own_years:.1f}년 — 상한 {ctx.tenure_limit_years}년 초과")
    if group_years > ctx.affiliate_tenure_limit_years:
        fails.append(
            f"계열 합산 재직 {group_years:.1f}년 — 상한 {ctx.affiliate_tenure_limit_years}년 초과"
        )
    ok = (
        f"자사 재직 {own_years:.1f}년(상한 {ctx.tenure_limit_years}년), "
        f"계열 합산 {group_years:.1f}년(상한 {ctx.affiliate_tenure_limit_years}년)"
    )
    return _verdict("R-05", fails, warns, ok)


def rule_r06(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """형 확정·제재·부정거래. 확인된(verified) 부정 이슈만 판정한다."""
    fail_cats = set(ctx.r06_fail_categories)
    fails: list[str] = []
    warns: list[str] = []
    resolved: list[str] = []
    unverified = 0
    for r in data.reputations:
        if r.polarity != "부정":
            continue
        if not r.verified_yn:
            unverified += 1
            continue
        when = r.event_date.isoformat() if r.event_date else "시점 미상"
        label = f"{r.category or '부정 이슈'}({when}, {r.status or '진행경과 미상'})"
        if r.status == "확정" and r.category in fail_cats:
            fails.append(f"확정된 결격 유형 이슈: {label}")
        elif r.status in ("무혐의", "종결"):
            resolved.append(label)
        else:
            warns.append(f"확인된 부정 이슈 — 법무 확인 필요: {label}")
    note = f" (사실관계 미확인 보도 {unverified}건은 판정에 반영하지 않음)" if unverified else ""
    if fails or warns:
        v = _verdict("R-06", fails, warns, "")
        return RuleVerdict("R-06", v.result, (v.reason or "") + note)
    ok = "확인된 부정 이슈 없음" + (f" — 종결·무혐의 {len(resolved)}건" if resolved else "")
    return RuleVerdict("R-06", C.SCREEN_PASS, ok + note)


def rule_r07(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """감사위원 회계·재무 전문가 요건 — 참고 정보."""
    grounds: list[str] = []
    certs = [c for c in data.certifications if c in ctx.audit_expert_certs]
    if certs:
        grounds.append("자격 " + ", ".join(certs))
    jobs = [p.title for p in data.positions if getattr(p, "job_l2_code", None) in ctx.audit_expert_jobs]
    if jobs:
        grounds.append("경력 " + ", ".join(dict.fromkeys(jobs)))
    exps = [
        code
        for code in data.expertise_codes
        if any(code.startswith(prefix) for prefix in ctx.audit_expert_expertise)
    ]
    if exps:
        grounds.append("전문분야 " + ", ".join(exps))
    if grounds:
        return RuleVerdict(
            "R-07", C.SCREEN_INFO, "회계·재무 전문가 요건 충족 가능 — 근거: " + " / ".join(grounds)
        )
    return RuleVerdict("R-07", C.SCREEN_INFO, "회계·재무 전문가 요건 근거 없음 — 감사위원 선임 시 별도 확인")


def rule_r08(ctx: OrgContext, data: ScreeningInput, today: date) -> RuleVerdict:
    """이사회 특정 성 단독 구성 금지 대상 여부 — 다양성 참고 정보."""
    if ctx.total_assets_krw < ctx.gender_rule_asset_threshold_krw:
        return RuleVerdict("R-08", C.SCREEN_INFO, "자사가 이사회 성별 구성 규정 대상 기준 미만")
    if ctx.board_female_count > 0:
        return RuleVerdict("R-08", C.SCREEN_INFO, "자사 이사회 성별 구성 요건 충족 상태")
    if data.gender == "F":
        return RuleVerdict("R-08", C.SCREEN_INFO, "다양성 기여 — 자사 이사회 특정 성 단독 구성 해소")
    if data.gender == "M":
        return RuleVerdict(
            "R-08", C.SCREEN_INFO, "다양성 경고 — 자사 이사회가 한 성으로만 구성되어 있어 남성 후보 선임만으로는 해소 불가"
        )
    return RuleVerdict("R-08", C.SCREEN_INFO, "성별 정보 없음 — 다양성 영향 판단 불가")


RULES: list[tuple[str, Callable[[OrgContext, ScreeningInput, date], RuleVerdict]]] = [
    ("R-01", rule_r01),
    ("R-02", rule_r02),
    ("R-03", rule_r03),
    ("R-04", rule_r04),
    ("R-05", rule_r05),
    ("R-06", rule_r06),
    ("R-07", rule_r07),
    ("R-08", rule_r08),
]


# ------------------------------------------------------------------ 집계

def worst(results: list[str]) -> str:
    """여러 룰 판정 중 가장 나쁜 것을 후보의 대표 상태로 본다.

    info(참고)는 대표 상태에 영향을 주지 않는다.
    """
    judged = [r for r in results if r != C.SCREEN_INFO]
    if not judged:
        return C.SCREEN_PASS
    return max(judged, key=lambda r: C.SCREEN_ORDER.get(r, 0))


def effective(row: ScreeningResult) -> str:
    """법무 수기 판정이 있으면 그것이 우선한다."""
    return row.reviewer_override or row.result


def status_of(person_id: int) -> str:
    with session_scope() as s:
        rows = s.execute(
            select(func.coalesce(ScreeningResult.reviewer_override, ScreeningResult.result)).where(
                ScreeningResult.person_id == person_id
            )
        ).scalars()
        return worst(list(rows))


def verdicts_of(person_id: int) -> list[ScreeningResult]:
    with session_scope() as s:
        return list(
            s.execute(
                select(ScreeningResult)
                .where(ScreeningResult.person_id == person_id)
                .order_by(ScreeningResult.rule_id)
            ).scalars()
        )


# ------------------------------------------------------------------ 실행

def evaluate_input(
    data: ScreeningInput, ctx: OrgContext, today: date | None = None
) -> list[RuleVerdict]:
    today = today or date.today()
    return [fn(ctx, data, today) for _, fn in RULES]


def evaluate(person_id: int, today: date | None = None, ctx: OrgContext | None = None) -> list[RuleVerdict]:
    from data.repository import get_person_detail

    detail = get_person_detail(person_id)
    if detail is None:
        raise LookupError(f"후보를 찾을 수 없습니다: person_id={person_id}")
    return evaluate_input(ScreeningInput.from_detail(detail), ctx or OrgContext.load(), today)


def evaluate_and_store(
    person_id: int, today: date | None = None, ctx: OrgContext | None = None
) -> list[RuleVerdict]:
    """판정하고 저장한다. 수기 판정(reviewer_override)이 있는 행은 보존한다."""
    verdicts = evaluate(person_id, today, ctx)
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        existing = {
            row.rule_id: row
            for row in s.execute(
                select(ScreeningResult).where(ScreeningResult.person_id == person_id)
            ).scalars()
        }
        for v in verdicts:
            row = existing.pop(v.rule_id, None)
            if row is None:
                s.add(
                    ScreeningResult(
                        person_id=person_id,
                        rule_id=v.rule_id,
                        result=v.result,
                        reason=v.reason,
                        evaluated_at=now,
                    )
                )
            else:
                row.result = v.result
                row.reason = v.reason
                row.evaluated_at = now
        # 현재 룰셋에 없는 옛 판정은 지운다. 단 수기 판정은 남긴다.
        for row in existing.values():
            if row.reviewer_override is None:
                s.delete(row)
    return verdicts


def evaluate_all(today: date | None = None) -> dict[str, int]:
    """전체 후보 재판정 (배치용, PRD F-09-8). 대표 상태별 인원을 반환한다."""
    ctx = OrgContext.load()
    with session_scope() as s:
        ids = list(s.execute(select(Person.person_id).order_by(Person.person_id)).scalars())
    counts = {C.SCREEN_PASS: 0, C.SCREEN_WARN: 0, C.SCREEN_FAIL: 0}
    for pid in ids:
        verdicts = evaluate_and_store(pid, today, ctx)
        counts[worst([v.result for v in verdicts])] += 1
    return counts


def set_override(person_id: int, rule_id: str, result: str | None, reason: str | None) -> None:
    """법무 수기 판정 입력/해제. 사유 없는 판정 변경은 받지 않는다."""
    if result is not None:
        if result not in (C.SCREEN_PASS, C.SCREEN_WARN, C.SCREEN_FAIL):
            raise ValueError(f"허용되지 않는 판정입니다: {result}")
        if not reason or not reason.strip():
            raise ValueError("수기 판정에는 사유가 필요합니다.")
    with session_scope() as s:
        row = s.execute(
            select(ScreeningResult).where(
                ScreeningResult.person_id == person_id, ScreeningResult.rule_id == rule_id
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError(f"판정 결과가 없습니다: {person_id}/{rule_id}")
        row.reviewer_override = result
        row.override_reason = reason.strip() if result is not None and reason else None
