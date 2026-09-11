"""POOL 관리 테스트 (PRD F-07, F-02-2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core import pools as P
from data.models import Person, ShareLink
from data.session import session_scope


def _people(n: int) -> list[int]:
    with session_scope() as s:
        return list(s.execute(select(Person.person_id).order_by(Person.person_id).limit(n)).scalars())


@pytest.fixture
def pool_id():
    return P.create_pool("테스트 POOL", user_id=1, purpose="테스트", target_position="감사위원", target_count=2)


def test_create_requires_name():
    with pytest.raises(ValueError):
        P.create_pool("  ", user_id=1)


def test_add_members_skips_duplicates(pool_id):
    ids = _people(3)
    assert P.add_members(pool_id, ids, user_id=1) == (3, 0)
    assert P.add_members(pool_id, ids[:2] + ids[:1], user_id=1) == (0, 2)
    assert {m.person_id for m in P.members(pool_id)} == set(ids)
    assert all(m.state == P.FLOW[0] for m in P.members(pool_id))


def test_allowed_transitions():
    assert P.allowed_transitions("후보 등록") == ["1차 검토", "보류", "제외"]
    assert "사추위 보고" not in P.allowed_transitions("후보 등록")
    assert "법무 검증" in P.allowed_transitions("사추위 보고")  # 한 단계 되돌리기
    assert P.allowed_transitions("제외") == ["후보 등록"]
    assert set(P.FLOW) <= set(P.allowed_transitions("보류"))


def test_state_change_rules(pool_id):
    pid = _people(1)[0]
    P.add_members(pool_id, [pid], user_id=1)
    P.change_state(pool_id, pid, "1차 검토", user_id=1)
    with pytest.raises(ValueError):
        P.change_state(pool_id, pid, "접촉", user_id=1)          # 단계 건너뛰기
    with pytest.raises(ValueError):
        P.change_state(pool_id, pid, "제외", user_id=1)          # 사유 없음
    P.change_state(pool_id, pid, "제외", user_id=1, reason="겸직 한도 초과로 제외")
    m = next(x for x in P.members(pool_id) if x.person_id == pid)
    assert m.state == "제외" and m.reason == "겸직 한도 초과로 제외"
    events = [e.event for e in P.timeline(pool_id)]
    assert events.count("상태변경") == 2 and "추가" in events


def test_concurrent_update_is_rejected(pool_id):
    pid = _people(1)[0]
    P.add_members(pool_id, [pid], user_id=1)
    P.change_state(pool_id, pid, "1차 검토", user_id=1, expected_state="후보 등록")
    # 다른 사용자는 아직 '후보 등록' 화면을 보고 있다
    with pytest.raises(P.ConcurrentUpdateError):
        P.change_state(pool_id, pid, "보류", user_id=2, reason="확인 대기", expected_state="후보 등록")


def test_comment_and_update(pool_id):
    with pytest.raises(ValueError):
        P.add_comment(pool_id, " ", user_id=1)
    P.add_comment(pool_id, "사추위 일정 확정", user_id=1)
    P.update_pool(pool_id, user_id=1, target_count=4)
    assert P.get_pool(pool_id).target_count == 4
    with pytest.raises(ValueError):
        P.update_pool(pool_id, user_id=1, created_by=99)


def test_delete_blocked_when_shared(pool_id):
    with session_scope() as s:
        s.add(ShareLink(pool_id=pool_id, recipient_email="x@example.com", purpose="t",
                        token_hash="h", expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    with pytest.raises(ValueError):
        P.delete_pool(pool_id, user_id=1)


def test_delete_unshared_pool():
    pid = P.create_pool("삭제용 POOL", user_id=1)
    P.add_members(pid, _people(2), user_id=1)
    P.delete_pool(pid, user_id=1)
    assert P.get_pool(pid) is None
