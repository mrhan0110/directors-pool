"""권한 로직 테스트 (PRD F-09-11, F-09-12, F-09-13)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import constants as C
from core.auth import (
    PAGE_PERMISSIONS,
    accessible_pages,
    can_access,
    can_download,
    is_session_expired,
)


def test_anonymous_has_no_access():
    for page in PAGE_PERMISSIONS:
        assert can_access(None, page) is False


def test_unknown_page_is_blocked_by_default():
    # 등록되지 않은 페이지는 fail-closed
    assert can_access(C.ROLE_ADMIN, "not_registered_page") is False


def test_admin_only_page():
    assert can_access(C.ROLE_ADMIN, "admin")
    for role in (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_VIEWER):
        assert can_access(role, "admin") is False


def test_viewer_cannot_search_or_download():
    assert can_access(C.ROLE_VIEWER, "search") is False
    assert can_access(C.ROLE_VIEWER, "review") is False
    assert can_access(C.ROLE_VIEWER, "share") is False
    assert can_download(C.ROLE_VIEWER) is False


def test_viewer_can_see_pool_and_detail():
    assert can_access(C.ROLE_VIEWER, "pool")
    assert can_access(C.ROLE_VIEWER, "detail")


def test_staff_can_download():
    assert can_download(C.ROLE_STAFF)


def test_accessible_pages_is_subset():
    for role in C.ALL_ROLES:
        pages = accessible_pages(role)
        assert set(pages) <= set(PAGE_PERMISSIONS)
        assert all(can_access(role, p) for p in pages)


def test_session_expiry():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    assert is_session_expired(None, 30, now) is True
    assert is_session_expired(now - timedelta(minutes=29), 30, now) is False
    assert is_session_expired(now - timedelta(minutes=31), 30, now) is True


def test_session_expiry_handles_naive_datetime():
    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 11, 11, 0)  # tz 없음 → UTC 로 간주
    assert is_session_expired(naive, 30, now) is True
