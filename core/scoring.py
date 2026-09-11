"""적합도 점수 (PRD F-06). 보조 지표다.

구성(가중치는 AppSetting): 전문분야 매칭도 + 이사회 스킬 갭 보완도 + 경력 수준 + 가용성 − 리스크 감점.

- 검색 조건과 무관한 부분(기본 점수)은 배치로 계산해 PersonScore 에 저장한다.
- 전문분야 매칭도는 검색 조건마다 달라지므로 검색 시 SQL 식으로 더한다.
  → '정렬 후 상위 N명'을 SQL LIMIT 으로 자르는 구조(F-09-5-1)를 유지한다.
- 전문분야 조건을 고르지 않으면 매칭도는 모든 후보에게 0이다(순위에 영향 없음).
  스킬 공백 기준으로 대신 계산하면 스킬갭 항목과 이중 계산되기 때문이다.
- 미확인 평판은 반영하지 않는다. 리스크는 스크리닝 판정(확인된 사실만 사용)에서 가져온다.
- 결격(🔴) 후보는 점수와 무관하게 목록 하단으로 분리한다(core/search.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Float, case, cast, exists, func, literal, select

from core import codes as CODES
from core import constants as C
from core import settings
from core.screening import _matches_any
from data.models import Expertise, Person, PersonScore
from data.session import session_scope

DISCLAIMER = "적합도 점수는 보조 지표이며, 최종 판단은 담당자·법무 검토로 확정됩니다."
NOT_COMPUTED_LABEL = "미산출"
NOT_IMPLEMENTED_LABEL = NOT_COMPUTED_LABEL  # 1단계 화면 호환

# 직급별 경력 수준 비율 (CodeMaster ROLE_LEVEL 코드 기준)
LEVEL_POINTS = {"L1": 1.0, "L2": 0.75, "L3": 0.5, "L4": 0.25}
SECONDARY_EXPERTISE_RATIO = 0.5  # 보조 전문분야는 스킬 공백을 절반만 채운 것으로 본다
RISK_PER_WARN = 0.5              # 확인 필요 1건당 리스크 감점 비율


@dataclass(frozen=True)
class Weights:
    expertise: float
    skill_gap: float
    career: float
    availability: float
    risk: float

    @classmethod
    def load(cls) -> "Weights":
        return cls(
            expertise=float(settings.get_int(C.SET_W_EXPERTISE)),
            skill_gap=float(settings.get_int(C.SET_W_SKILL_GAP)),
            career=float(settings.get_int(C.SET_W_CAREER)),
            availability=float(settings.get_int(C.SET_W_AVAILABILITY)),
            risk=float(settings.get_int(C.SET_W_RISK)),
        )


@dataclass(frozen=True)
class ScoreContext:
    weights: Weights
    skill_gaps: tuple[str, ...]
    concurrent_limit: int
    attendance_warn_rate: float
    own_orgs: tuple[str, ...]

    @classmethod
    def load(cls) -> "ScoreContext":
        return cls(
            weights=Weights.load(),
            skill_gaps=tuple(settings.get_list(C.SET_BOARD_SKILL_GAPS)),
            concurrent_limit=settings.get_int(C.SET_CONCURRENT_LIMIT),
            attendance_warn_rate=settings.get_float(C.SET_ATTENDANCE_WARN_RATE),
            own_orgs=(settings.get_str(C.SET_OWN_COMPANY), *settings.get_list(C.SET_AFFILIATES)),
        )


@dataclass
class ScoreInput:
    expertise: list[tuple[str, bool]] = field(default_factory=list)  # (코드, 대표 여부)
    positions: list[Any] = field(default_factory=list)
    directorships: list[Any] = field(default_factory=list)
    screening_results: list[str] = field(default_factory=list)       # 수기 판정 반영된 결과

    @classmethod
    def from_detail(cls, detail) -> "ScoreInput":
        from core import expertise as EXP
        from core.screening import effective

        shown = EXP.displayable(detail.expertises, detail.sources)  # 근거 없는 전문분야는 점수에도 안 쓴다
        return cls(
            expertise=[(e.taxonomy_code, bool(e.is_primary)) for e in shown],
            positions=list(detail.positions),
            directorships=list(detail.directorships),
            screening_results=[effective(s) for s in detail.screenings],
        )


# ------------------------------------------------------------------ 구성 요소

def skill_gap_component(data: ScoreInput, ctx: ScoreContext) -> tuple[float, str]:
    w = ctx.weights.skill_gap
    if not ctx.skill_gaps:
        return 0.0, "이사회 스킬 공백 미설정"
    held: dict[str, float] = {}
    for code, primary in data.expertise:
        held[code] = max(held.get(code, 0.0), 1.0 if primary else SECONDARY_EXPERTISE_RATIO)
    matched = [g for g in ctx.skill_gaps if g in held]
    ratio = min(1.0, sum(held[g] for g in matched) / len(ctx.skill_gaps))
    reason = f"스킬 공백 {len(ctx.skill_gaps)}개 중 {len(matched)}개 보유"
    if matched:
        reason += " (" + ", ".join(CODES.label_of(C.CODE_EXPERTISE_L2, g) for g in matched) + ")"
    return round(w * ratio, 2), reason


def career_component(data: ScoreInput, ctx: ScoreContext) -> tuple[float, str]:
    w = ctx.weights.career
    levels = [p.role_level for p in data.positions if p.role_level in LEVEL_POINTS]
    if not levels:
        return 0.0, "직급 정보 없음"
    best = max(levels, key=LEVEL_POINTS.__getitem__)
    return round(w * LEVEL_POINTS[best], 2), f"최고 직급 {CODES.label_of(C.CODE_ROLE_LEVEL, best)}"


def availability_component(data: ScoreInput, ctx: ScoreContext) -> tuple[float, str]:
    w = ctx.weights.availability
    current = [d for d in data.directorships if d.is_current]
    listed = [d for d in current if d.listed_yn and not _matches_any(d.company_name, ctx.own_orgs)]
    n, limit = len(listed), ctx.concurrent_limit
    if n == 0:
        ratio = 1.0
    else:
        ratio = max(0.0, (limit - n) / limit) if limit > 0 else 0.0
    reason = f"현 상장사 겸직 {n}건(한도 {limit}건)"
    rates = [d.board_attendance_rate for d in current if d.board_attendance_rate is not None]
    if rates:
        avg = sum(rates) / len(rates)
        reason += f", 평균 출석률 {avg:.0%}"
        if avg < ctx.attendance_warn_rate:
            ratio *= 0.5
            reason += f" (기준 {ctx.attendance_warn_rate:.0%} 미만 감점)"
    return round(w * ratio, 2), reason


def risk_component(data: ScoreInput, ctx: ScoreContext) -> tuple[float, str]:
    """감점 크기(양수)를 반환한다. 참고(info) 판정은 반영하지 않는다."""
    w = ctx.weights.risk
    judged = [r for r in data.screening_results if r != C.SCREEN_INFO]
    if C.SCREEN_FAIL in judged:
        return w, "결격 가능 판정 — 최대 감점"
    warns = judged.count(C.SCREEN_WARN)
    if warns:
        return round(min(w, w * RISK_PER_WARN * warns), 2), f"확인 필요 판정 {warns}건"
    return 0.0, "스크리닝 이슈 없음"


def base_score(data: ScoreInput, ctx: ScoreContext) -> tuple[float, dict]:
    sg, sg_r = skill_gap_component(data, ctx)
    cr, cr_r = career_component(data, ctx)
    av, av_r = availability_component(data, ctx)
    rk, rk_r = risk_component(data, ctx)
    total = round(sg + cr + av - rk, 2)
    w = ctx.weights
    breakdown = {
        "skill_gap": {"points": sg, "max": w.skill_gap, "reason": sg_r},
        "career": {"points": cr, "max": w.career, "reason": cr_r},
        "availability": {"points": av, "max": w.availability, "reason": av_r},
        "risk": {"points": -rk, "max": w.risk, "reason": rk_r},
        "expertise_weight": w.expertise,
    }
    return total, breakdown


# ------------------------------------------------------------------ 저장 (배치)

def store(person_id: int, ctx: ScoreContext | None = None) -> float:
    from data.repository import get_person_detail

    detail = get_person_detail(person_id)
    if detail is None:
        raise LookupError(f"후보를 찾을 수 없습니다: person_id={person_id}")
    score, breakdown = base_score(ScoreInput.from_detail(detail), ctx or ScoreContext.load())
    now = datetime.now(timezone.utc)
    with session_scope() as s:
        row = s.get(PersonScore, person_id)
        if row is None:
            s.add(PersonScore(person_id=person_id, base_score=score, breakdown=breakdown, computed_at=now))
        else:
            row.base_score = score
            row.breakdown = breakdown
            row.computed_at = now
    return score


def score_all() -> int:
    """전체 후보 기본 점수 재산출 (배치용, PRD F-09-8)."""
    ctx = ScoreContext.load()
    with session_scope() as s:
        ids = list(s.execute(select(Person.person_id)).scalars())
    for pid in ids:
        store(pid, ctx)
    return len(ids)


def get(person_id: int) -> PersonScore | None:
    with session_scope() as s:
        return s.get(PersonScore, person_id)


def fit_score(person_id: int) -> float | None:
    """기본 점수. 없으면 None('미산출')."""
    row = get(person_id)
    return row.base_score if row else None


def breakdowns_in(s, ids: list[int]) -> dict[int, dict]:
    """person_id → {'base': 기본점수, 'breakdown': 근거}. 검색 결과 표시용."""
    if not ids:
        return {}
    rows = s.execute(select(PersonScore).where(PersonScore.person_id.in_(ids))).scalars()
    return {r.person_id: {"base": r.base_score, "breakdown": r.breakdown} for r in rows}


# ------------------------------------------------------------------ 검색용 SQL 식

def _has_evidence():
    return func.trim(Expertise.evidence_snippet) != ""


def expertise_match_expr(f: dict, weight: float):
    """선택한 전문분야 중 보유 비율 × 가중치. 근거 없는 전문분야는 세지 않는다."""
    l2 = list(f.get("expertise_l2") or [])
    l1 = list(f.get("expertise_l1") or [])
    if l2:
        cnt = (
            select(func.count(Expertise.expertise_id))
            .where(
                Expertise.person_id == Person.person_id,
                Expertise.taxonomy_code.in_(l2),
                _has_evidence(),
            )
            .correlate(Person)
            .scalar_subquery()
        )
        return cast(cnt, Float) * (weight / len(l2))
    if l1:
        terms = [
            case(
                (
                    exists()
                    .where(
                        Expertise.person_id == Person.person_id,
                        Expertise.taxonomy_code.like(f"{code}%"),
                        _has_evidence(),
                    )
                    .correlate(Person),
                    1.0,
                ),
                else_=0.0,
            )
            for code in l1
        ]
        total = terms[0]
        for t in terms[1:]:
            total = total + t
        return total * (weight / len(l1))
    return literal(0.0, Float)


def base_score_expr():
    return func.coalesce(
        select(PersonScore.base_score)
        .where(PersonScore.person_id == Person.person_id)
        .correlate(Person)
        .scalar_subquery(),
        0.0,
    )


def fit_expr(f: dict, weights: Weights | None = None):
    w = weights or Weights.load()
    return base_score_expr() + expertise_match_expr(f, w.expertise)


def display(score: float | None) -> str:
    if score is None:
        return NOT_COMPUTED_LABEL
    return f"{max(0, min(100, round(score)))}"


def describe(breakdown: dict, match_points: float) -> str:
    """점수 근거 요약 (PRD §6.2 '근거 요약')."""
    parts = []
    if match_points:
        parts.append(f"전문분야 매칭 +{match_points:.0f}")
    for key, label in (("skill_gap", "스킬갭"), ("career", "경력"), ("availability", "가용성")):
        pts = breakdown.get(key, {}).get("points", 0)
        parts.append(f"{label} +{pts:.0f}")
    risk = breakdown.get("risk", {}).get("points", 0)
    if risk:
        parts.append(f"리스크 {risk:.0f}")
    return " · ".join(parts)
