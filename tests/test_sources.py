"""출처 충돌·최신성 테스트 (PRD F-05-3, F-05-4)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace as NS

import pytest

from core import constants as C
from core import sources as SRC

TODAY = date(2026, 9, 11)
POLICY = SRC.FreshnessPolicy(disclosure_days=460, news_years=3, web_days=365)


def src(tier, published=None, collected=None):
    return NS(source_tier=tier, published_date=published,
              collected_at=datetime.combine(collected, datetime.min.time()) if collected else None)


@pytest.mark.parametrize(
    "s,expected",
    [
        (src(C.SOURCE_TIER_A, published=date(2026, 3, 18)), False),
        (src(C.SOURCE_TIER_A, published=date(2025, 1, 1)), True),
        (src(C.SOURCE_TIER_B, collected=date(2026, 1, 1)), False),
        (src(C.SOURCE_TIER_B, collected=date(2025, 1, 1)), True),
        (src(C.SOURCE_TIER_C, published=date(2023, 9, 11)), False),   # 정확히 3년 = 경계 안
        (src(C.SOURCE_TIER_C, published=date(2023, 9, 10)), True),
        (src(C.SOURCE_TIER_C), True),                                  # 날짜 미상
    ],
)
def test_is_outdated(s, expected):
    assert SRC.is_outdated(s, POLICY, TODAY) is expected


def test_resolve_prefers_higher_tier_and_keeps_alternative():
    a = src(C.SOURCE_TIER_A, published=date(2025, 3, 1))
    c = src(C.SOURCE_TIER_C, published=date(2026, 8, 1))
    adopted, alts = SRC.resolve([("부사장", c), ("전무", a)])
    assert adopted == ("전무", a)
    assert alts == [("부사장", c)]


def test_resolve_same_value_is_not_conflict():
    a = src(C.SOURCE_TIER_A, published=date(2025, 3, 1))
    b = src(C.SOURCE_TIER_B, published=date(2025, 5, 1))
    _, alts = SRC.resolve([("전무", a), ("전무", b)])
    assert alts == []


def test_resolve_same_tier_prefers_recent():
    old = src(C.SOURCE_TIER_C, published=date(2024, 1, 1))
    new = src(C.SOURCE_TIER_C, published=date(2026, 1, 1))
    adopted, _ = SRC.resolve([("A", old), ("B", new)])
    assert adopted[0] == "B"


def test_resolve_requires_source():
    with pytest.raises(ValueError):
        SRC.resolve([])


def test_seeded_conflict_is_exposed():
    """시드의 3번 후보는 공시(A)와 언론(C)의 직위가 다르다."""
    conflicts = SRC.conflicts_of(3)
    assert conflicts, "시드 충돌 케이스가 조회되지 않음"
    c = conflicts[0]
    assert c.adopted_source.source_tier == C.SOURCE_TIER_A
    assert c.alt_source.source_tier == C.SOURCE_TIER_C
    assert c.alt_value != c.adopted_value
    assert SRC.conflict_index(conflicts)[(c.entity, c.entity_id)] == [c]
