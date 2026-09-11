"""검수 워크플로우 테스트 (PRD F-08-1 ~ F-08-4, 인수 기준 #8)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from core import constants as C
from core import expertise as EXP
from core import review as R
from data.models import Expertise, Person, Position, Reputation, ReviewLog, ReviewQueue, Source
from data.session import session_scope


@pytest.fixture
def pid():
    """검수 대상 가상 후보 1명 (경력 1, 평판 1, 전문분야 1)."""
    with session_scope() as s:
        src = Source(publisher="금융감독원 전자공시시스템", doc_title="검수 테스트",
                     url="https://dart.example.com/review", source_tier=C.SOURCE_TIER_A, quote_snippet="인용")
        person = Person(name_ko="가상검수 테스트", nationality=["KR"])
        s.add_all([src, person])
        s.flush()
        s.add(Position(person_id=person.person_id, org_name="가상전자", title="전무", role_level="L2",
                       is_current=True, start_date=date(2020, 1, 1), source_id=src.source_id))
        s.add(Reputation(person_id=person.person_id, polarity="긍정", summary="수상", verified_yn=True,
                         source_id=src.source_id))
        s.add(EXP.build(person.person_id, "EXP_FIN_01", "재무전략 총괄", src.source_id, is_primary=True))
        return person.person_id


def _ids(pid):
    items = R.items_of(pid)
    return {e: getattr(row, R._PK[e]) for e, row in items}


def test_progress_and_completion_gate(pid):
    prog = R.progress(pid)
    assert (prog.total, prog.processed, prog.done) == (3, 0, False)
    with pytest.raises(ValueError):
        R.complete(pid, user_id=1)


def test_full_review_flow(pid):
    ids = _ids(pid)
    R.approve(pid, "position", ids["position"], user_id=1)
    R.edit(pid, "reputation", ids["reputation"], "summary", "정부 포상 수상", user_id=1)
    R.delete(pid, "expertise", ids["expertise"], user_id=1, reason="근거 문구가 담당 업무와 무관")
    assert R.progress(pid).done
    R.complete(pid, user_id=1)
    with session_scope() as s:
        assert s.get(Person, pid).profile_status == C.PROFILE_REVIEWED
        rep = s.get(Reputation, ids["reputation"])
        assert rep.summary == "정부 포상 수상" and rep.manually_edited
        assert s.execute(select(Expertise).where(Expertise.person_id == pid)).first() is None
        actions = [r.action for r in s.execute(select(ReviewLog).where(ReviewLog.person_id == pid)).scalars()]
    assert {C.REVIEW_APPROVE, C.REVIEW_EDIT, C.REVIEW_DELETE} <= set(actions)
    assert any(h.action == EXP.ACTION_DELETE for h in EXP.history_of(pid))

    with pytest.raises(ValueError):
        R.reopen(pid, user_id=1, reason=" ")
    R.reopen(pid, user_id=1, reason="신규 공시 반영")
    with session_scope() as s:
        assert s.get(Person, pid).profile_status == C.PROFILE_UNREVIEWED


def test_edit_validation(pid):
    ids = _ids(pid)
    with pytest.raises(ValueError):
        R.edit(pid, "position", ids["position"], "source_id", 1, user_id=1)   # 출처는 못 바꾼다
    with pytest.raises(ValueError):
        R.edit(pid, "position", ids["position"], "title", "  ", user_id=1)    # 필수값
    with pytest.raises(LookupError):
        R.edit(pid + 999, "position", ids["position"], "title", "상무", user_id=1)  # 다른 후보 항목
    R.edit(pid, "position", ids["position"], "start_date", "2019-03-01", user_id=1)
    with session_scope() as s:
        assert s.get(Position, ids["position"]).start_date == date(2019, 3, 1)


def test_delete_requires_reason(pid):
    with pytest.raises(ValueError):
        R.delete(pid, "position", _ids(pid)["position"], user_id=1, reason="")


def test_conflict_alert_blocks_completion_until_resolved(pid):
    ids = _ids(pid)
    for entity, eid in ids.items():
        R.approve(pid, entity, eid, user_id=1)
    with session_scope() as s:
        s.add(ReviewQueue(queue_type=C.QUEUE_CONFLICT, payload={
            "person_id": pid, "entity": "position", "entity_id": ids["position"], "field": "title",
            "current_value": "전무", "new_value": "부사장"}))
    assert R.open_alerts(pid)
    with pytest.raises(ValueError):
        R.complete(pid, user_id=1)
    R.resolve_alert(R.open_alerts(pid)[0].id, user_id=1, accept_new=True)
    with session_scope() as s:
        assert s.get(Position, ids["position"]).title == "부사장"
    R.complete(pid, user_id=1)
