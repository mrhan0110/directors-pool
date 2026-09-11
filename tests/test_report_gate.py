"""리포트 출력 게이트 테스트 (PRD F-08-1, F-09-9, F-09-12, 인수 기준 #8)."""

from __future__ import annotations

from core import constants as C
from reports.builder import check_export


def test_blocked_for_viewer():
    gate = check_export(C.ROLE_VIEWER, [C.PROFILE_REVIEWED])
    assert gate.allowed is False
    assert "외부뷰어" in gate.reason


def test_blocked_when_unreviewed_present():
    gate = check_export(C.ROLE_STAFF, [C.PROFILE_REVIEWED, C.PROFILE_UNREVIEWED])
    assert gate.allowed is False
    assert "검수 미완료" in gate.reason


def test_allowed_when_all_reviewed():
    gate = check_export(C.ROLE_STAFF, [C.PROFILE_REVIEWED, C.PROFILE_REVIEWED])
    assert gate.allowed is True
    assert gate.reason is None


def test_blocked_for_anonymous():
    gate = check_export(None, [C.PROFILE_REVIEWED])
    assert gate.allowed is False
