"""선정 고려사항 18개 체크리스트 테스트 (PRD F-03 (7), F-03-5)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest

from core import considerations as CS
from core import constants as C
from core import scoring
from core.screening import effective, worst
from data.repository import get_person_detail

TODAY = date(2026, 9, 11)


def fake_detail(screenings=(), directorships=(), positions=(), **person):
    p = dict(gender="F", nationality=["KR"], nationality_primary="KR", residence_region="R_CAPITAL")
    p.update(person)
    return NS(person=NS(**p), positions=list(positions), directorships=list(directorships),
              screenings=list(screenings))


def test_items_match_prd_table():
    assert [no for no, *_ in CS.ITEMS] == list(range(1, 19))
    manual = {no for no, _, _, mode in CS.ITEMS if mode == CS.MANUAL}
    assert manual == {10, 11, 12, 14, 16, 17}


def test_seeded_person_evaluation():
    detail = get_person_detail(1)
    row = scoring.get(1)
    items = CS.evaluate(detail, row.breakdown if row else None, TODAY)
    assert len(items) == 18
    for it in items:
        if it.mode == CS.MANUAL:
            assert it.signal is None, "수기 항목에 자동 신호가 붙음"
    legal = [effective(s) for s in detail.screenings if s.rule_id in ("R-01", "R-02", "R-03", "R-04", "R-05", "R-06")]
    assert items[2].signal == worst(legal)
    assert "점" in items[6].auto_text


def test_no_screening_means_no_signal():
    items = CS.evaluate(fake_detail(), None, TODAY)
    assert items[0].signal is None and "미실행" in items[0].auto_text
    assert items[6].signal is None and "미산출" in items[6].auto_text


def test_low_attendance_is_warn():
    d = NS(is_current=True, board_attendance_rate=0.5, term_end_date=None, compensation_disclosed=None,
           company_name="타사")
    items = CS.evaluate(fake_detail(directorships=[d]), None, TODAY)
    assert items[4].signal == C.SCREEN_WARN


def test_recent_public_office_hint():
    gov = NS(job_l1_code="GOV", is_current=False, end_date=date(2025, 1, 1), org_name="금융감독원(가상)",
             title="국장", is_full_time=True)
    items = CS.evaluate(fake_detail(positions=[gov]), None, TODAY)
    assert items[9].signal is None
    assert "취업제한" in items[9].auto_text


def test_save_check_roundtrip_and_validation():
    CS.save_check(1, 11, user_id=1, status="확인 필요", comment="자문사 반대 권고 이력 확인 중",
                  attachment_name="memo.txt", attachment=b"reference memo")
    row = CS.get_checks(1)[11]
    assert row.status == "확인 필요" and row.attachment_name == "memo.txt"
    CS.save_check(1, 11, user_id=1, comment="확인 완료")
    assert CS.get_checks(1)[11].status == "확인 필요"  # 상태는 유지
    with pytest.raises(ValueError):
        CS.save_check(1, 19, user_id=1, status="이상 없음")
    with pytest.raises(ValueError):
        CS.save_check(1, 11, user_id=1, status="아무거나")
    with pytest.raises(ValueError):
        CS.save_check(1, 11, user_id=1, attachment=b"x" * (CS.MAX_ATTACHMENT_BYTES + 1))
