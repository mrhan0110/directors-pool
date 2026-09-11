"""상세 화면 보조 로직 테스트 (PRD F-03-1, F-03 (5))."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest

from core import career
from core import reputation as REP
from core.auth import can_override_screening, can_review
from core import constants as C


@pytest.mark.parametrize(
    "months,label",
    [(None, "임기 만료일 미상"), (-3, "이미 만료 (3개월 경과)"), (0, "0년 0개월"), (5, "0년 5개월"), (29, "2년 5개월")],
)
def test_remaining_label(months, label):
    assert career.remaining_label(months) == label


def rep(polarity, verified, year, category="언론 인터뷰", status=None, summary="요약"):
    return NS(polarity=polarity, verified_yn=verified, event_date=date(year, 5, 1),
              category=category, status=status, summary=summary)


def test_signals_separate_unverified():
    s = REP.signals([
        rep("긍정", True, 2024), rep("부정", False, 2025, "규제 제재"),
        rep("부정", True, 2025, "법적 분쟁"), rep("중립", True, 2025),
    ])
    assert s.verified == 3 and s.unverified == 1 and s.verified_negative == 1
    assert s.by_year[2025] == {"긍정": 0, "중립": 1, "부정": 2}
    assert list(s.by_year) == [2024, 2025]


def test_status_parts_marks_unverified_and_final_result():
    parts = REP.status_parts(rep("부정", False, 2025, status="진행중", summary="제재 보도"))
    assert "사실관계 미확인" in parts["사실관계"]
    assert parts["최종 결과"] == "미확정"
    assert REP.status_parts(rep("부정", True, 2025, status="무혐의"))["최종 결과"] == "무혐의"


def test_review_and_override_roles():
    assert can_review(C.ROLE_LEGAL) and not can_review(C.ROLE_VIEWER)
    assert can_override_screening(C.ROLE_LEGAL) and can_override_screening(C.ROLE_ADMIN)
    assert not can_override_screening(C.ROLE_STAFF)
