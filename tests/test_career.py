"""경력 표출 규칙 테스트 (PRD F-03 (3)).

경계값을 명시적으로 검증한다. 인수 기준 #3 이 이 로직에 걸려 있다.
"""

from __future__ import annotations

from datetime import date

from core.career import build_view, is_executive, within_lookback
from data.models import Position

TODAY = date(2026, 9, 11)


def pos(**kw) -> Position:
    base = dict(
        person_id=1,
        org_name="가상회사",
        title="상무",
        role_level="L3",
        is_registered_officer=False,
        start_date=date(2020, 1, 1),
        end_date=date(2023, 1, 1),
        is_current=False,
        is_highlight=False,
        source_id=1,
    )
    base.update(kw)
    return Position(**base)


def test_executive_by_role_level():
    assert is_executive(pos(role_level="L1"))
    assert is_executive(pos(role_level="L3"))
    assert not is_executive(pos(role_level="L4", is_registered_officer=False))


def test_executive_by_registered_officer():
    # 직급 등급이 낮아도 등기임원이면 포함한다
    assert is_executive(pos(role_level="L4", is_registered_officer=True))


def test_lookback_boundary_exactly_ten_years():
    # 정확히 10년 전 종료 = 포함 (경계 포함)
    assert within_lookback(pos(end_date=date(2016, 9, 11)), 10, TODAY)
    # 10년 + 1일 전 종료 = 제외
    assert not within_lookback(pos(end_date=date(2016, 9, 10)), 10, TODAY)


def test_lookback_open_ended_is_included():
    # 종료일 없음 = 현직으로 간주하여 포함
    assert within_lookback(pos(end_date=None), 10, TODAY)


def test_build_view_splits_recent_highlight_excluded():
    positions = [
        pos(end_date=date(2024, 1, 1), role_level="L2"),            # 최근 + 임원 → recent
        pos(end_date=date(2005, 1, 1), role_level="L1", is_highlight=True),  # 초과 + 하이라이트
        pos(end_date=date(2024, 1, 1), role_level="L4"),            # 최근이지만 비임원 → 제외
        pos(end_date=date(2000, 1, 1), role_level="L2"),            # 초과 + 하이라이트 아님 → 제외
    ]
    view = build_view(positions, today=TODAY, lookback_years=10)
    assert len(view.recent) == 1
    assert len(view.highlights) == 1
    assert view.excluded_count == 2


def test_recent_sorted_desc_by_start_date():
    positions = [
        pos(start_date=date(2018, 1, 1), end_date=date(2020, 1, 1), role_level="L2"),
        pos(start_date=date(2022, 1, 1), end_date=date(2024, 1, 1), role_level="L2"),
    ]
    view = build_view(positions, today=TODAY, lookback_years=10)
    assert [p.start_date.year for p in view.recent] == [2022, 2018]
