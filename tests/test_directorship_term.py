"""잔여 임기 계산 테스트 (PRD F-03-1, 인수 기준 #4).

월말·윤년·이미 만료된 건·임기만료일 미상을 모두 검증한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from data.models import Directorship


def d(term_end: date | None) -> Directorship:
    return Directorship(
        person_id=1,
        company_name="가상회사",
        role_type="사외이사",
        term_end_date=term_end,
        source_id=1,
    )


def test_none_when_term_end_unknown():
    assert d(None).remaining_term_months() is None


def test_exact_months():
    assert d(date(2027, 3, 11)).remaining_term_months(today=date(2026, 9, 11)) == 6


def test_partial_month_rounds_down():
    # 만료일의 일자가 기준일보다 이르면 한 달을 깎는다
    assert d(date(2027, 3, 10)).remaining_term_months(today=date(2026, 9, 11)) == 5


def test_already_expired_returns_negative():
    assert d(date(2026, 6, 11)).remaining_term_months(today=date(2026, 9, 11)) == -3


def test_same_day_is_zero():
    assert d(date(2026, 9, 11)).remaining_term_months(today=date(2026, 9, 11)) == 0


def test_leap_day_does_not_crash():
    assert d(date(2028, 2, 29)).remaining_term_months(today=date(2026, 9, 11)) == 17


@pytest.mark.parametrize(
    "term_end,today,expected",
    [
        (date(2026, 10, 31), date(2026, 9, 30), 1),
        (date(2026, 10, 1), date(2026, 9, 30), 0),   # 한 달 못 채움
        (date(2027, 1, 1), date(2026, 12, 31), 0),
    ],
)
def test_month_end_cases(term_end, today, expected):
    assert d(term_end).remaining_term_months(today=today) == expected
