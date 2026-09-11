"""전문분야 자동 분류 (PRD F-04, §6.4 분류 로직).

흐름: 근거 단위 추출(Evidence) → 택소노미 매핑(규칙 사전 + 선택적 LLM) → 최신성×출처 가중 합산
     → 상위 3개 대표 / 나머지 보조 → build() 가드를 통과한 것만 저장.

환각 방지 (불변규칙 2, 분류 로직 5)
- 모든 분류는 원문 근거 스니펫 + source_id 를 가진다. 근거가 없으면 분류 자체가 생기지 않는다.
- LLM 결과는 스니펫이 실제 근거 원문에 그대로 존재할 때만 채택한다.
- 화면 출력 직전에도 displayable() 로 한 번 더 거른다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Protocol

from sqlalchemy import select

from core import codes as CODES
from core import constants as C
from core.expertise_rules import JOB_HINTS, KEYWORDS
from data.models import Expertise, ExpertiseHistory
from data.session import session_scope

MAX_PRIMARY = 3  # 대표 전문분야 최대 개수 (PRD F-04)

# 근거 최신성 가중 (PRD §6.4 분류 로직 3): (경과 연수 상한, 가중치)
RECENCY_WEIGHTS = ((5, 1.0), (10, 0.6), (None, 0.3))
# 출처 신뢰도 가중 (PRD §6.5 등급)
TIER_WEIGHTS = {C.SOURCE_TIER_A: 1.0, C.SOURCE_TIER_B: 0.8, C.SOURCE_TIER_C: 0.5}
# 신뢰도(상/중/하) 산정 기준: (최소 가중점수, 최소 근거 건수)
CONFIDENCE_RULES = (("상", 2.0, 2), ("중", 1.0, 1))
SNIPPET_MAX = 200

ACTION_CONFIRM = "확정"
ACTION_PRIMARY = "대표지정"
ACTION_SECONDARY = "보조지정"
ACTION_DELETE = "삭제"


class MissingEvidenceError(ValueError):
    """근거 스니펫 없이 전문분야를 부여하려 할 때."""


# ------------------------------------------------------------------ 저장 가드 (1단계부터 유지)

def validate_taxonomy_code(code: str) -> str:
    """택소노미에 없는 코드는 거부한다. 자유 텍스트 금지 (PRD F-04-1)."""
    valid = set(CODES.code_map(C.CODE_EXPERTISE_L1)) | set(CODES.code_map(C.CODE_EXPERTISE_L2))
    if code not in valid:
        raise ValueError(f"택소노미에 없는 전문분야 코드입니다: {code}")
    return code


def build(
    person_id: int,
    taxonomy_code: str,
    evidence_snippet: str,
    source_id: int,
    *,
    level: str = "중",
    confidence: str = "중",
    evidence_count: int = 1,
    is_primary: bool = False,
    score: float = 0.0,
    extra_source_ids: list[int] | None = None,
) -> Expertise:
    """Expertise 생성의 유일한 통로. 여기를 우회해 생성하지 말 것."""
    validate_taxonomy_code(taxonomy_code)
    if not evidence_snippet or not evidence_snippet.strip():
        raise MissingEvidenceError(
            f"근거 스니펫 없이 전문분야를 부여할 수 없습니다 "
            f"(person_id={person_id}, code={taxonomy_code}). PRD F-04-2"
        )
    if not source_id:
        raise MissingEvidenceError("출처 없이 전문분야를 저장할 수 없습니다. PRD F-05-1")
    return Expertise(
        person_id=person_id,
        taxonomy_code=taxonomy_code,
        level=level,
        confidence=confidence,
        evidence_count=evidence_count,
        evidence_snippet=evidence_snippet.strip(),
        is_primary=is_primary,
        score=score,
        source_id=source_id,
        extra_source_ids=list(extra_source_ids or []),
    )


def displayable(expertises: Iterable[Expertise], sources: dict) -> list[Expertise]:
    """화면·리포트 출력 직전 가드. 근거 스니펫 또는 출처 URL 이 없으면 내보내지 않는다."""
    out = []
    for e in expertises:
        src = sources.get(e.source_id)
        if not (e.evidence_snippet and e.evidence_snippet.strip()):
            continue
        if src is None or not getattr(src, "url", None):
            continue
        out.append(e)
    return out


# ------------------------------------------------------------------ 분류 로직

@dataclass(frozen=True)
class Evidence:
    """근거 단위 1건 (PRD §6.4 분류 로직 1)."""

    text: str
    source_id: int
    evidence_date: date | None
    tier: str
    job_l2_code: str | None = None


@dataclass
class Classified:
    code: str
    score: float
    evidence_count: int
    snippet: str
    source_id: int
    extra_source_ids: list[int] = field(default_factory=list)
    confidence: str = "하"
    is_primary: bool = False


def recency_weight(evidence_date: date | None, today: date) -> float:
    """최근 5년 1.0 / 6~10년 0.6 / 10년 초과 0.3. 날짜 미상은 가장 낮은 가중."""
    if evidence_date is None:
        return RECENCY_WEIGHTS[-1][1]
    years = (today - evidence_date).days / 365.25
    for limit, weight in RECENCY_WEIGHTS:
        if limit is None or years <= limit:
            return weight
    return RECENCY_WEIGHTS[-1][1]  # pragma: no cover


def match_codes(text: str, job_l2_code: str | None = None) -> dict[str, str]:
    """원문에서 매칭된 택소노미 코드 → 매칭 키워드."""
    hits: dict[str, str] = {}
    for code, words in KEYWORDS.items():
        for w in words:
            if w in text:
                hits[code] = w
                break
    hint = JOB_HINTS.get(job_l2_code or "")
    if hint and hint not in hits:
        hits[hint] = f"직업구분:{job_l2_code}"
    return hits


def _confidence(score: float, count: int) -> str:
    for label, min_score, min_count in CONFIDENCE_RULES:
        if score >= min_score and count >= min_count:
            return label
    return "하"


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_MAX else text[: SNIPPET_MAX - 1] + "…"


def classify_evidence(evidences: Iterable[Evidence], today: date | None = None) -> list[Classified]:
    """근거 목록 → 가중 점수순 분류 결과. 근거가 없으면 빈 목록 (환각 차단)."""
    today = today or date.today()
    acc: dict[str, dict] = {}
    for ev in evidences:
        if not ev.text or not ev.text.strip() or not ev.source_id:
            continue  # 근거·출처 없는 원문은 분류에 쓰지 않는다
        w = recency_weight(ev.evidence_date, today) * TIER_WEIGHTS.get(ev.tier, 0.5)
        for code in match_codes(ev.text, ev.job_l2_code):
            slot = acc.setdefault(code, {"score": 0.0, "count": 0, "best": None, "sources": []})
            slot["score"] += w
            slot["count"] += 1
            slot["sources"].append(ev.source_id)
            if slot["best"] is None or w > slot["best"][0]:
                slot["best"] = (w, ev)
    out: list[Classified] = []
    for code, slot in acc.items():
        best_ev: Evidence = slot["best"][1]
        extras = [sid for sid in dict.fromkeys(slot["sources"]) if sid != best_ev.source_id]
        out.append(
            Classified(
                code=code,
                score=round(slot["score"], 3),
                evidence_count=slot["count"],
                snippet=_snippet(best_ev.text),
                source_id=best_ev.source_id,
                extra_source_ids=extras,
                confidence=_confidence(slot["score"], slot["count"]),
            )
        )
    out.sort(key=lambda c: (-c.score, -c.evidence_count, c.code))
    for i, c in enumerate(out):
        c.is_primary = i < MAX_PRIMARY
    return out


def _period_end(period: str | None) -> date | None:
    """'2019~2023' 같은 기간 문자열의 종료 연도."""
    if not period:
        return None
    digits = [p for p in period.replace("~", " ").replace("-", " ").split() if p.isdigit() and len(p) == 4]
    return date(int(digits[-1]), 12, 31) if digits else None


def evidence_from_detail(detail, today: date | None = None) -> list[Evidence]:
    """상세 프로파일에서 근거 단위를 뽑는다. 출처가 확인되지 않는 항목은 제외한다."""
    today = today or date.today()
    sources = detail.sources
    out: list[Evidence] = []
    for p in detail.positions:
        src = sources.get(p.source_id)
        if src is None:
            continue
        text = " ".join(x for x in (p.org_name, p.title, p.duties or "") if x)
        when = today if p.is_current else (p.end_date or p.start_date)
        out.append(Evidence(text, p.source_id, when, src.source_tier, p.job_l2_code))
    for a in detail.achievements:
        src = sources.get(a.source_id)
        if src is None:
            continue
        text = " ".join(x for x in (a.category or "", a.description, a.quantitative_metric or "") if x)
        when = _period_end(a.period) or src.published_date
        out.append(Evidence(text, a.source_id, when, src.source_tier))
    return out


# ------------------------------------------------------------------ LLM 분류 (선택, 기본 off)

class LLMClassifier(Protocol):
    def classify(self, evidences: list[Evidence]) -> list[dict]:
        """[{code, snippet, source_id}] 형태를 반환한다."""
        ...


def llm_enabled() -> bool:
    """외부 LLM 사용 방식은 PRD §14-3 결정 대기다. 명시적으로 켜기 전까지 쓰지 않는다."""
    return os.getenv("EXPERTISE_LLM_ENABLED", "false").lower() == "true"


def verify_llm_items(items: list[dict], evidences: list[Evidence]) -> list[dict]:
    """LLM 이 낸 스니펫이 실제 근거 원문에 그대로 있을 때만 채택한다 (환각 차단)."""
    by_source: dict[int, list[str]] = {}
    for ev in evidences:
        by_source.setdefault(ev.source_id, []).append(ev.text)
    valid_codes = set(KEYWORDS)
    accepted = []
    for it in items:
        snippet = (it.get("snippet") or "").strip()
        texts = by_source.get(it.get("source_id"), [])
        if it.get("code") in valid_codes and snippet and any(snippet in t for t in texts):
            accepted.append(it)
    return accepted


# ------------------------------------------------------------------ 저장 / 담당자 수정

def _user_deleted_codes(s, person_id: int) -> set[str]:
    """담당자가 삭제한 코드. 마지막 이력이 '삭제'면 재분류가 다시 넣지 않는다 (F-04-4)."""
    rows = s.execute(
        select(ExpertiseHistory.taxonomy_code, ExpertiseHistory.action)
        .where(ExpertiseHistory.person_id == person_id)
        .order_by(ExpertiseHistory.occurred_at, ExpertiseHistory.id)
    ).all()
    last: dict[str, str] = {}
    for code, action in rows:
        last[code] = action
    return {code for code, action in last.items() if action == ACTION_DELETE}


def classify(person_id: int, today: date | None = None) -> list[Classified]:
    from data.repository import get_person_detail

    detail = get_person_detail(person_id)
    if detail is None:
        raise LookupError(f"후보를 찾을 수 없습니다: person_id={person_id}")
    return classify_evidence(evidence_from_detail(detail, today), today)


def store(person_id: int, today: date | None = None) -> list[Classified]:
    """자동 분류 결과를 저장한다.

    담당자가 확정·수정한 행은 건드리지 않고, 담당자가 삭제한 코드는 다시 넣지 않는다.
    대표 3개 자리는 확정된 대표를 먼저 채우고 남은 자리를 자동 결과로 채운다.
    """
    results = classify(person_id, today)
    with session_scope() as s:
        existing = list(s.execute(select(Expertise).where(Expertise.person_id == person_id)).scalars())
        locked = {e.taxonomy_code: e for e in existing if e.confirmed_by_user_yn or e.manually_edited}
        for e in existing:
            if e.taxonomy_code not in locked:
                s.delete(e)
        s.flush()

        deleted = _user_deleted_codes(s, person_id)
        slots = MAX_PRIMARY - sum(1 for e in locked.values() if e.is_primary)
        kept: list[Classified] = []
        for c in results:
            if c.code in locked or c.code in deleted:
                continue
            c.is_primary = slots > 0
            slots -= 1 if c.is_primary else 0
            s.add(
                build(
                    person_id,
                    c.code,
                    c.snippet,
                    c.source_id,
                    confidence=c.confidence,
                    evidence_count=c.evidence_count,
                    is_primary=c.is_primary,
                    score=c.score,
                    extra_source_ids=c.extra_source_ids,
                )
            )
            kept.append(c)
    return kept


def classify_all(today: date | None = None) -> int:
    """전체 후보 재분류 (배치용, PRD F-09-8). 저장한 분류 건수를 반환한다."""
    from data.models import Person

    with session_scope() as s:
        ids = list(s.execute(select(Person.person_id)).scalars())
    return sum(len(store(pid, today)) for pid in ids)


def _history(s, person_id: int, code: str, action: str, before: str | None, after: str | None,
             user_id: int | None) -> None:
    s.add(
        ExpertiseHistory(
            person_id=person_id,
            taxonomy_code=code,
            action=action,
            before_value=before,
            after_value=after,
            user_id=user_id,
        )
    )


def _get(s, person_id: int, code: str) -> Expertise:
    row = s.execute(
        select(Expertise).where(Expertise.person_id == person_id, Expertise.taxonomy_code == code)
    ).scalar_one_or_none()
    if row is None:
        raise LookupError(f"전문분야가 없습니다: {person_id}/{code}")
    return row


def confirm(person_id: int, code: str, user_id: int | None) -> None:
    """담당자 확정. 이후 자동 재분류가 덮어쓰지 않는다 (F-04-4)."""
    with session_scope() as s:
        row = _get(s, person_id, code)
        row.confirmed_by_user_yn = True
        _history(s, person_id, code, ACTION_CONFIRM, "자동", "확정", user_id)


def set_primary(person_id: int, code: str, primary: bool, user_id: int | None) -> None:
    """대표/보조 지정. 대표는 최대 3개."""
    with session_scope() as s:
        row = _get(s, person_id, code)
        if primary and not row.is_primary:
            n = sum(
                1
                for e in s.execute(select(Expertise).where(Expertise.person_id == person_id)).scalars()
                if e.is_primary
            )
            if n >= MAX_PRIMARY:
                raise ValueError(f"대표 전문분야는 최대 {MAX_PRIMARY}개입니다. 다른 항목을 보조로 먼저 바꾸세요.")
        before = "대표" if row.is_primary else "보조"
        row.is_primary = primary
        row.manually_edited = True
        _history(s, person_id, code, ACTION_PRIMARY if primary else ACTION_SECONDARY,
                 before, "대표" if primary else "보조", user_id)


def remove(person_id: int, code: str, user_id: int | None, reason: str) -> None:
    """담당자 삭제. 사유 필수, 이후 재분류가 같은 코드를 다시 넣지 않는다."""
    if not reason or not reason.strip():
        raise ValueError("전문분야 삭제에는 사유가 필요합니다.")
    with session_scope() as s:
        row = _get(s, person_id, code)
        before = f"{row.evidence_snippet} (신뢰도 {row.confidence})"
        s.delete(row)
        _history(s, person_id, code, ACTION_DELETE, before, reason.strip(), user_id)


def history_of(person_id: int) -> list[ExpertiseHistory]:
    with session_scope() as s:
        return list(
            s.execute(
                select(ExpertiseHistory)
                .where(ExpertiseHistory.person_id == person_id)
                .order_by(ExpertiseHistory.occurred_at.desc(), ExpertiseHistory.id.desc())
            ).scalars()
        )
