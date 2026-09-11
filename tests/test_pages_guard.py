"""페이지 가드 테스트 (PRD F-09-11, 인수 기준 #10·#11).

Streamlit AppTest 로 페이지 스크립트를 직접 실행한다.
'URL 직접 접근' 시나리오를 코드 레벨에서 재현하는 것에 해당한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from core import constants as C
from core.auth import CurrentUser
from core.state import K_LAST_ACTIVE, K_USER

PAGE_FILES = {
    "dashboard": "pages/0_대시보드.py",
    "search": "pages/1_후보_검색.py",
    "detail": "pages/2_후보_상세.py",
    "compare": "pages/3_후보_비교.py",
    "pool": "pages/4_POOL_관리.py",
    "review": "pages/5_검수.py",
    "report": "pages/6_리포트.py",
    "admin": "pages/7_관리자.py",
    "share": "pages/8_공유_관리.py",
}


def _user(role: str) -> CurrentUser:
    return CurrentUser(user_id=1, email="t@example.com", display_name="테스트", role=role)


def _run(path: str, role: str | None):
    at = AppTest.from_file(str(PROJECT_ROOT / path), default_timeout=30)
    if role is not None:
        from datetime import datetime, timezone

        at.session_state[K_USER] = _user(role)
        at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    return at.run()


@pytest.mark.parametrize("page_key,path", PAGE_FILES.items())
def test_anonymous_access_is_blocked(page_key, path):
    """로그아웃 상태로 모든 페이지에 직접 접근해도 데이터가 노출되지 않는다."""
    at = _run(path, None)
    assert not at.exception, f"{path} 에서 예외 발생: {at.exception}"
    errors = [e.value for e in at.error]
    assert any("로그인이 필요" in msg for msg in errors), f"{path} 가 로그인 요구를 하지 않음"
    # 데이터 표출 위젯이 하나도 없어야 한다
    assert len(at.dataframe) == 0, f"{path} 가 비로그인 상태에서 데이터를 표시함"


@pytest.mark.parametrize("page_key,path", PAGE_FILES.items())
def test_admin_can_open_every_page(page_key, path):
    """관리자는 전 페이지를 예외 없이 열 수 있다."""
    at = _run(path, C.ROLE_ADMIN)
    assert not at.exception, f"{path} 에서 예외 발생: {at.exception}"


@pytest.mark.parametrize(
    "page_key,path",
    [(k, v) for k, v in PAGE_FILES.items() if k in ("search", "review", "admin", "share")],
)
def test_viewer_is_denied_restricted_pages(page_key, path):
    """외부뷰어는 검색·검수·관리자·공유 페이지에 접근할 수 없다 (PRD F-09-12)."""
    at = _run(path, C.ROLE_VIEWER)
    assert not at.exception
    errors = [e.value for e in at.error]
    assert any("권한이 없" in msg for msg in errors), f"{path} 가 외부뷰어를 차단하지 않음"
    assert len(at.dataframe) == 0


def test_staff_is_denied_admin_page():
    at = _run(PAGE_FILES["admin"], C.ROLE_STAFF)
    assert not at.exception
    assert any("권한이 없" in e.value for e in at.error)


def test_idle_session_is_logged_out():
    """유휴 세션은 자동 로그아웃된다 (PRD F-09-13)."""
    from datetime import datetime, timedelta, timezone

    at = AppTest.from_file(str(PROJECT_ROOT / PAGE_FILES["dashboard"]), default_timeout=30)
    at.session_state[K_USER] = _user(C.ROLE_STAFF)
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc) - timedelta(hours=2)
    at.run()
    assert not at.exception
    assert any("자동 로그아웃" in w.value for w in at.warning)
    assert len(at.dataframe) == 0
