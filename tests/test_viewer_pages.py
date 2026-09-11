"""외부뷰어·계정 재검증 화면 테스트 (PRD F-09-11·12, 인수 기준 #11, 부록 C #2·#3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from core import access, pools
from core import constants as C
from core.auth import CurrentUser
from core.state import K_LAST_ACTIVE, K_SELECTED_PERSON, K_USER
from data.models import AppUser, Person
from data.session import session_scope
from tests.helpers import user_for

ROOT = Path(__file__).resolve().parent.parent


def _run(path: str, user: CurrentUser, selected_person: int | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / path), default_timeout=60)
    at.session_state[K_USER] = user
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    if selected_person is not None:
        at.session_state[K_SELECTED_PERSON] = selected_person
    return at.run()


def _all_ids() -> list[int]:
    with session_scope() as s:
        return list(s.execute(select(Person.person_id)).scalars())


def test_viewer_detail_ignores_out_of_scope_person():
    """URL/세션 조작으로 범위 밖 후보를 지정해도 열리지 않는다."""
    viewer = user_for(C.ROLE_VIEWER)
    allowed = access.allowed_person_ids(viewer)
    assert allowed, "시드 공유 POOL 이 없음"
    outsider = next(pid for pid in _all_ids() if pid not in allowed)
    at = _run("pages/2_후보_상세.py", viewer, selected_person=outsider)
    assert not at.exception
    value = at.selectbox(key="detail_person").value
    assert value in allowed and value != outsider
    assert len(at.selectbox(key="detail_person").options) == len(allowed)


def test_viewer_pool_page_is_read_only_and_scoped():
    viewer = user_for(C.ROLE_VIEWER)
    at = _run("pages/4_POOL_관리.py", viewer)
    assert not at.exception
    shared = pools.list_pools(access.allowed_pool_ids(viewer))
    assert len(at.selectbox(key="pool_select").options) == len(shared)
    assert len(at.text_input) == 0 and len(at.text_area) == 0, "외부뷰어에게 편집 입력란이 노출됨"


def test_viewer_dashboard_hides_global_statistics():
    at = _run("pages/0_대시보드.py", user_for(C.ROLE_VIEWER))
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "등록 후보" not in labels
    assert len(at.dataframe) == 0


def test_viewer_without_share_sees_nothing():
    with session_scope() as s:
        u = s.execute(select(AppUser).where(AppUser.email == "tmp-viewer@example.com")).scalar_one_or_none()
        if u is None:
            u = AppUser(email="tmp-viewer@example.com", display_name="임시 뷰어", role=C.ROLE_VIEWER,
                        expires_at=date.today() + timedelta(days=10))
            s.add(u)
            s.flush()
        uid = u.user_id
    tmp = CurrentUser(uid, "tmp-viewer@example.com", "임시 뷰어", C.ROLE_VIEWER)
    for path, msg in (("pages/2_후보_상세.py", "열람 가능한 후보"), ("pages/4_POOL_관리.py", "열람 가능한 POOL")):
        at = _run(path, tmp)
        assert not at.exception
        assert any(msg in i.value for i in at.info), f"{path}: 범위 없음 안내가 없음"
        assert len(at.dataframe) == 0


def test_tampered_session_role_is_not_trusted():
    """세션의 역할을 관리자로 바꿔도 DB 역할(담당자)로 판단한다."""
    staff = user_for(C.ROLE_STAFF)
    forged = CurrentUser(staff.user_id, staff.email, staff.display_name, C.ROLE_ADMIN)
    at = _run("pages/7_관리자.py", forged)
    assert not at.exception
    assert any("권한이 없" in e.value for e in at.error)
    assert len(at.dataframe) == 0


def test_deactivated_account_is_blocked_mid_session():
    staff = user_for(C.ROLE_STAFF)
    with session_scope() as s:
        s.get(AppUser, staff.user_id).is_active = False
    try:
        at = _run("pages/0_대시보드.py", staff)
        assert not at.exception
        assert any("비활성화" in e.value for e in at.error)
        assert len(at.dataframe) == 0
    finally:
        with session_scope() as s:
            s.get(AppUser, staff.user_id).is_active = True
