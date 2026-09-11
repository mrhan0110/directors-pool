"""출처 표시·충돌 규칙 (PRD F-05-2 ~ F-05-4).

- 충돌: 상위 신뢰등급(A 공시 > B 기관 > C 언론)을 채택하고, 하위 값은 '대체 정보'로 병기한다.
  충돌 사실을 숨기지 않는다.
- 최신성: 공시는 최근 사업보고서 기준, 언론은 최근 N년, 홈페이지는 수집일 기준. 초과 시 '구 정보'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

from sqlalchemy import select

from core import constants as C
from core import settings
from core.screening import years_ago
from data.models import FieldConflict, Source
from data.session import session_scope

OUTDATED_LABEL = "구 정보"


@dataclass(frozen=True)
class FreshnessPolicy:
    disclosure_days: int
    news_years: int
    web_days: int

    @classmethod
    def load(cls) -> "FreshnessPolicy":
        return cls(
            disclosure_days=settings.get_int(C.SET_DISCLOSURE_FRESH_DAYS, default=460),
            news_years=settings.get_int(C.SET_NEWS_FRESH_YEARS),
            web_days=settings.get_int(C.SET_WEB_FRESH_DAYS),
        )


def is_outdated(src: Source, policy: FreshnessPolicy, today: date | None = None) -> bool:
    """출처가 최신성 기준을 넘었는가 (F-05-4). 날짜를 알 수 없으면 구 정보로 본다."""
    today = today or date.today()
    if src.source_tier == C.SOURCE_TIER_A:
        ref = src.published_date or (src.collected_at.date() if src.collected_at else None)
        return ref is None or ref < today - timedelta(days=policy.disclosure_days)
    if src.source_tier == C.SOURCE_TIER_B:
        ref = src.collected_at.date() if src.collected_at else None
        return ref is None or ref < today - timedelta(days=policy.web_days)
    ref = src.published_date
    return ref is None or ref < years_ago(today, policy.news_years)


def resolve(candidates: Sequence[tuple[Any, Source]]) -> tuple[tuple[Any, Source], list[tuple[Any, Source]]]:
    """(값, 출처) 후보 중 채택값과 대체 정보를 고른다 (F-05-3).

    등급이 높을수록 우선, 같은 등급이면 발행일이 최근인 것을 우선한다.
    값이 같은 하위 출처는 충돌이 아니므로 대체 정보에서 뺀다.
    """
    if not candidates:
        raise ValueError("출처 없는 값은 채택할 수 없습니다. (PRD F-05-1)")
    ordered = sorted(
        candidates,
        key=lambda vs: (C.SOURCE_TIER_ORDER.get(vs[1].source_tier, 9), -(vs[1].published_date or date.min).toordinal()),
    )
    adopted = ordered[0]
    alternatives = [vs for vs in ordered[1:] if vs[0] != adopted[0]]
    return adopted, alternatives


@dataclass(frozen=True)
class ConflictView:
    entity: str
    entity_id: int | None
    field: str
    adopted_value: str | None
    adopted_source: Source | None
    alt_value: str | None
    alt_source: Source | None


def conflicts_of(person_id: int) -> list[ConflictView]:
    """후보의 출처 충돌 목록. 화면은 채택값 옆에 '대체 정보'로 병기한다."""
    with session_scope() as s:
        rows = list(s.execute(select(FieldConflict).where(FieldConflict.person_id == person_id)).scalars())
        ids = {r.adopted_source_id for r in rows} | {r.alt_source_id for r in rows}
        srcs = {x.source_id: x for x in s.execute(select(Source).where(Source.source_id.in_(ids))).scalars()} if ids else {}
    return [
        ConflictView(r.entity, r.entity_id, r.field, r.adopted_value, srcs.get(r.adopted_source_id),
                     r.alt_value, srcs.get(r.alt_source_id))
        for r in rows
    ]


def conflict_index(conflicts: list[ConflictView]) -> dict[tuple[str, int | None], list[ConflictView]]:
    """(entity, entity_id) → 충돌 목록. 화면에서 해당 항목 옆에 붙이기 위함."""
    out: dict[tuple[str, int | None], list[ConflictView]] = {}
    for c in conflicts:
        out.setdefault((c.entity, c.entity_id), []).append(c)
    return out
