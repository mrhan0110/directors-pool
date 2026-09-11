"""공유 링크·외부뷰어 범위 테스트 (PRD F-09-12, F-09-14~16, 인수 기준 #11·#12, 부록 C #3·#4)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core import access, auth, pools, settings, sharing
from core import constants as C
from data.models import AccessLog, AppUser, Person, ShareLink
from data.session import session_scope
from tests.helpers import user_for

TODAY = date.today()


def _people(n):
    with session_scope() as s:
        return list(s.execute(select(Person.person_id).order_by(Person.person_id).limit(n)).scalars())


@pytest.fixture
def shared_pool():
    """외부뷰어에게 공유된 POOL (구성원 2명)."""
    staff = user_for(C.ROLE_STAFF)
    viewer = user_for(C.ROLE_VIEWER)
    pool_id = pools.create_pool("공유 테스트 POOL", staff.user_id)
    members = _people(2)
    pools.add_members(pool_id, members, staff.user_id)
    issued = sharing.issue_link(pool_id, staff.user_id, viewer.email, "사추위원 사전 검토", TODAY + timedelta(days=10))
    return {"pool_id": pool_id, "members": members, "issued": issued, "staff": staff, "viewer": viewer}


# ------------------------------------------------------------------ 발급 검증 (F-09-15)

@pytest.mark.parametrize(
    "email,purpose,days,msg",
    [
        ("not-an-email", "목적", 10, "이메일"),
        ("viewer@example.com", "  ", 10, "목적"),
        ("viewer@example.com", "목적", 0, "오늘 이후"),
        ("viewer@example.com", "목적", 9999, "최대"),
        ("nobody@example.com", "목적", 10, "계정"),
    ],
)
def test_issue_validation(email, purpose, days, msg):
    pool_id = pools.create_pool("검증용 POOL", 1)
    with pytest.raises(ValueError, match=msg):
        sharing.issue_link(pool_id, 1, email, purpose, TODAY + timedelta(days=days))


def test_token_is_stored_only_as_hash(shared_pool):
    token = shared_pool["issued"].token
    with session_scope() as s:
        link = s.get(ShareLink, shared_pool["issued"].share_id)
        assert link.token_hash == sharing.hash_token(token)
        assert token not in link.token_hash
    assert shared_pool["issued"].url.endswith(f"?share={token}")


def test_issue_is_logged(shared_pool):
    with session_scope() as s:
        actions = list(s.execute(select(AccessLog.action).where(
            AccessLog.share_id == shared_pool["issued"].share_id)).scalars())
    assert C.ACT_SHARE_ISSUE in actions


# ------------------------------------------------------------------ 검증 (F-09-14)

def test_verify_requires_matching_recipient(shared_pool):
    viewer, staff = shared_pool["viewer"], shared_pool["staff"]
    share_id, pool_id = sharing.verify_token(shared_pool["issued"].token, viewer.user_id, viewer.email)
    assert pool_id == shared_pool["pool_id"]
    with pytest.raises(sharing.ShareDenied, match="다른 수신자"):
        sharing.verify_token(shared_pool["issued"].token, staff.user_id, staff.email)
    with pytest.raises(sharing.ShareDenied, match="유효하지 않은"):
        sharing.verify_token("forged-token", viewer.user_id, viewer.email)
    with session_scope() as s:
        assert s.get(ShareLink, share_id).access_count == 1


def test_expired_link_is_denied(shared_pool):
    viewer = shared_pool["viewer"]
    later = datetime.now(timezone.utc) + timedelta(days=11)
    with pytest.raises(sharing.ShareDenied, match="만료"):
        sharing.verify_token(shared_pool["issued"].token, viewer.user_id, viewer.email, now=later)
    assert all(l.share_id != shared_pool["issued"].share_id
               for l in sharing.active_links_for(viewer.email, now=later))


# ------------------------------------------------------------------ 외부뷰어 범위 (F-09-12)

def test_viewer_scope_is_limited_to_shared_pool_members(shared_pool):
    viewer = shared_pool["viewer"]
    assert shared_pool["pool_id"] in access.allowed_pool_ids(viewer)
    allowed = access.allowed_person_ids(viewer)
    assert set(shared_pool["members"]) <= allowed
    outsider = max(_people(25))
    if outsider not in allowed:
        assert not access.can_view_person(viewer, outsider)
    assert access.filter_person_options(viewer, [(outsider, "x")]) == ([] if outsider not in allowed else [(outsider, "x")])


def test_internal_roles_are_unrestricted():
    staff = user_for(C.ROLE_STAFF)
    assert access.allowed_pool_ids(staff) is None
    assert access.can_view_person(staff, 1)
    assert access.allowed_pool_ids(None) == []


def test_revoke_blocks_on_next_request(shared_pool):
    """회수 즉시(재로그인 없이) 다음 요청부터 차단된다 (인수 기준 #12)."""
    viewer = shared_pool["viewer"]
    sharing.revoke(shared_pool["issued"].share_id, shared_pool["staff"].user_id)
    assert shared_pool["pool_id"] not in access.allowed_pool_ids(viewer)
    with pytest.raises(sharing.ShareDenied, match="회수"):
        sharing.verify_token(shared_pool["issued"].token, viewer.user_id, viewer.email)
    with session_scope() as s:
        link = s.get(ShareLink, shared_pool["issued"].share_id)
    assert sharing.status_of(link) == sharing.STATUS_REVOKED


def test_status_labels(shared_pool):
    with session_scope() as s:
        link = s.get(ShareLink, shared_pool["issued"].share_id)
    now = datetime.now(timezone.utc)
    assert sharing.status_of(link, now) == sharing.STATUS_ACTIVE
    assert sharing.status_of(link, now + timedelta(days=5)) == sharing.STATUS_SOON
    assert sharing.status_of(link, now + timedelta(days=12)) == sharing.STATUS_EXPIRED


# ------------------------------------------------------------------ 계정 재검증 (F-09-11·12)

def test_refresh_user_reflects_db_changes():
    viewer = user_for(C.ROLE_VIEWER)
    assert auth.refresh_user(viewer.user_id).role == C.ROLE_VIEWER
    with session_scope() as s:
        s.get(AppUser, viewer.user_id).is_active = False
    try:
        assert auth.refresh_user(viewer.user_id) is None
    finally:
        with session_scope() as s:
            s.get(AppUser, viewer.user_id).is_active = True


def test_refresh_user_rejects_expired_account():
    with session_scope() as s:
        expired = s.execute(select(AppUser).where(AppUser.email == "viewer-expired@example.com")).scalar_one()
    assert auth.refresh_user(expired.user_id) is None
