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


def test_search_reports_total_and_shown(monkeypatch):
    """빈 DB 에서도 total/shown 이 일관되게 보고되는지 확인."""
    result = search.search({}, "N10", C.ROLE_STAFF)
    assert result.shown == len(result.rows)
    assert result.shown <= result.effective_limit
    assert result.total_matched >= result.shown
