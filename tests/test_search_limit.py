"""최대 조회 인원 수 테스트 (PRD F-01-8, 인수 기준 #15·#16).

'단순 절단'이 아니라 '상위 N명'이어야 하고, '전체'도 시스템 상한을 넘지 못한다.
"""

from __future__ import annotations

import pytest

from core import constants as C
from core import search, settings
from core.search import resolve_limit


def test_default_when_no_selection():
    limit, capped = resolve_limit(None, C.ROLE_STAFF)
    assert limit == settings.get_int(C.SET_RESULT_LIMIT_DEFAULT)
    assert capped is None


@pytest.mark.parametrize("code,expected", [("N10", 10), ("N30", 30), ("N100", 100), ("N200", 200)])
def test_explicit_selection(code, expected):
    limit, capped = resolve_limit(code, C.ROLE_STAFF)
    assert limit == expected
    assert capped is None


def test_all_is_capped_by_system_max():
    system_max = settings.get_int(C.SET_RESULT_LIMIT_SYSTEM_MAX)
    limit, capped = resolve_limit("NALL", C.ROLE_STAFF)
    assert limit == system_max
    assert capped == "system"


def test_viewer_has_lower_cap():
    viewer_max = settings.get_int(C.SET_RESULT_LIMIT_VIEWER_MAX)
    limit, capped = resolve_limit("N200", C.ROLE_VIEWER)
    assert limit == viewer_max
    assert capped == "viewer"


def test_viewer_small_selection_is_not_capped():
    limit, capped = resolve_limit("N10", C.ROLE_VIEWER)
    assert limit == 10
    assert capped is None


def test_search_reports_total_and_shown():
    """shown 은 min(상한, 전체) — '전체 N명 중 상위 M명'의 M 이다 (F-01-8)."""
    result = search.search({}, "N10", C.ROLE_STAFF)
    assert result.shown == min(result.effective_limit, result.total_matched)
    assert len(result.rows) <= min(result.shown, result.page_size)
    assert result.total_matched >= result.shown
    assert result.truncated == (result.shown < result.total_matched)


def test_when_matches_fewer_than_limit_all_are_shown():
    """선택 인원 수보다 매칭이 적으면 매칭 수만 표시한다 (절단 아님)."""
    result = search.search({}, "N200", C.ROLE_STAFF)
    assert result.shown == result.total_matched
    assert not result.truncated


def test_zero_matches():
    result = search.search({"nationalities": ["CN"]}, "N30", C.ROLE_STAFF)
    assert result.total_matched == 0
    assert result.shown == 0
    assert result.rows == []
    assert result.page_count == 1
