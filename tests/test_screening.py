"""스크리닝 룰엔진 테스트 (PRD §5.1, R-01~R-08).

잘못된 결격 판정은 개인의 법적·평판 피해로 직결되므로 경계값과
'임계값을 설정에서 읽는가'를 중점적으로 검증한다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from core import constants as C
from core import screening as S
from core import settings
from data.models import Person, ScreeningResult
from data.session import session_scope

TODAY = date(2026, 9, 11)

CTX = S.OrgContext(
    own_company="자사홀딩스",
    affiliates=("자사홀딩스캐피탈", "자사물산"),
    major_shareholders=("대주주재단",),
    conflict_orgs=("감사인회계법인",),
    cooling_off_years=2,
    concurrent_limit=2,
    tenure_limit_years=6,
    affiliate_tenure_limit_years=9,
    total_assets_krw=3_000,
    gender_rule_asset_threshold_krw=2_000,
    board_female_count=0,
    r06_fail_categories=("규제 제재", "형사 판결"),
    audit_expert_certs=("공인회계사",),
    audit_expert_jobs=("ACCT_CPA", "CORP_CFO"),
    audit_expert_expertise=("EXP_FIN", "EXP_AUD"),
)


def pos(org, *, start=date(2010, 1, 1), end=None, current=False, full_time=True, title="상무", job=None):
    return NS(
        org_name=org, title=title, start_date=start, end_date=end,
        is_current=current, is_full_time=full_time, job_l2_code=job,
    )


def dirship(company, *, listed=True, current=True, appointed=date(2022, 3, 1), term_end=None):
    return NS(
        company_name=company, role_type="사외이사", appointed_date=appointed,
        term_end_date=term_end, is_current=current, listed_yn=listed,
    )


def rep(category, status, verified=True, polarity="부정"):
    return NS(polarity=polarity, category=category, status=status,
              verified_yn=verified, event_date=date(2025, 1, 1))


def data(**kw) -> S.ScreeningInput:
    return S.ScreeningInput(**kw)


# ------------------------------------------------------------------ R-01

def test_r01_current_full_time_at_own_company_fails():
    v = S.rule_r01(CTX, data(positions=[pos("자사홀딩스", current=True)]), TODAY)
    assert v.result == C.SCREEN_FAIL
    assert "현직 상근" in v.reason


def test_r01_current_part_time_is_warn_not_fail():
    v = S.rule_r01(CTX, data(positions=[pos("자사물산", current=True, full_time=False)]), TODAY)
    assert v.result == C.SCREEN_WARN


def test_r01_ended_exactly_at_cooling_off_boundary_fails():
    # 정확히 2년 전 종료 = 냉각기간 안 (경계 포함)
    v = S.rule_r01(CTX, data(positions=[pos("자사홀딩스", end=date(2024, 9, 11))]), TODAY)
    assert v.result == C.SCREEN_FAIL


def test_r01_ended_one_day_before_boundary_passes():
    v = S.rule_r01(CTX, data(positions=[pos("자사홀딩스", end=date(2024, 9, 10))]), TODAY)
    assert v.result == C.SCREEN_PASS


def test_r01_unknown_end_date_is_warn():
    v = S.rule_r01(CTX, data(positions=[pos("자사홀딩스캐피탈", end=None)]), TODAY)
    assert v.result == C.SCREEN_WARN


def test_r01_unrelated_company_passes():
    v = S.rule_r01(CTX, data(positions=[pos("무관전자", current=True)]), TODAY)
    assert v.result == C.SCREEN_PASS


def test_r01_name_containing_own_company_is_not_a_match():
    """회귀: '자사홀딩스재단'은 자사명을 포함하지만 자사가 아니다. 부분 포함 매칭은 오판을 만든다."""
    v = S.rule_r01(CTX, data(positions=[pos("자사홀딩스재단", current=True)]), TODAY)
    assert v.result == C.SCREEN_PASS


def test_r01_name_normalization():
    """'(주)'·공백 차이는 같은 회사로 본다."""
    v = S.rule_r01(CTX, data(positions=[pos("(주) 자사 홀딩스", current=True)]), TODAY)
    assert v.result == C.SCREEN_FAIL


def test_r01_cooling_off_comes_from_context():
    """냉각기간을 3년으로 늘리면 2.5년 전 종료도 결격 가능이 된다 (하드코딩 금지 확인)."""
    p = pos("자사홀딩스", end=date(2024, 3, 1))
    assert S.rule_r01(CTX, data(positions=[p]), TODAY).result == C.SCREEN_PASS
    ctx3 = replace(CTX, cooling_off_years=3)
    assert S.rule_r01(ctx3, data(positions=[p]), TODAY).result == C.SCREEN_FAIL


def test_years_ago_handles_leap_day():
    assert S.years_ago(date(2028, 2, 29), 2) == date(2026, 2, 28)


# ------------------------------------------------------------------ R-02 / R-03

def test_r02_current_at_major_shareholder_fails():
    v = S.rule_r02(CTX, data(positions=[pos("대주주재단", current=True)]), TODAY)
    assert v.result == C.SCREEN_FAIL


def test_r02_recent_past_is_warn():
    v = S.rule_r02(CTX, data(positions=[pos("대주주재단", end=date(2025, 12, 31))]), TODAY)
    assert v.result == C.SCREEN_WARN


def test_r03_conflict_never_auto_fails():
    v = S.rule_r03(CTX, data(positions=[pos("감사인회계법인", current=True)]), TODAY)
    assert v.result == C.SCREEN_WARN


def test_r03_old_conflict_passes():
    v = S.rule_r03(CTX, data(positions=[pos("감사인회계법인", end=date(2015, 1, 1))]), TODAY)
    assert v.result == C.SCREEN_PASS


# ------------------------------------------------------------------ R-04

@pytest.mark.parametrize("n,expected", [(0, C.SCREEN_PASS), (1, C.SCREEN_PASS), (2, C.SCREEN_WARN), (3, C.SCREEN_FAIL)])
def test_r04_listed_directorship_count(n, expected):
    dirs = [dirship(f"타사{i}") for i in range(n)]
    assert S.rule_r04(CTX, data(directorships=dirs), TODAY).result == expected


def test_r04_ignores_unlisted_ended_and_own_company():
    dirs = [
        dirship("타사A"),
        dirship("비상장B", listed=False),
        dirship("종료C", current=False),
        dirship("자사홀딩스"),
    ]
    assert S.rule_r04(CTX, data(directorships=dirs), TODAY).result == C.SCREEN_PASS


def test_r04_limit_comes_from_context():
    dirs = [dirship(f"타사{i}") for i in range(3)]
    assert S.rule_r04(replace(CTX, concurrent_limit=3), data(directorships=dirs), TODAY).result == C.SCREEN_WARN


# ------------------------------------------------------------------ R-05

def test_r05_own_tenure_over_limit_fails():
    d = dirship("자사홀딩스", appointed=date(2019, 1, 1))  # 7.7년
    v = S.rule_r05(CTX, data(directorships=[d]), TODAY)
    assert v.result == C.SCREEN_FAIL
    assert "자사 재직" in v.reason


def test_r05_affiliate_is_not_counted_as_own_but_counts_in_group():
    d1 = dirship("자사홀딩스캐피탈", appointed=date(2019, 1, 1))  # 7.7년 계열
    v = S.rule_r05(CTX, data(directorships=[d1]), TODAY)
    assert v.result == C.SCREEN_PASS  # 자사 0년, 계열 7.7년 < 9년
    d2 = dirship("자사홀딩스", appointed=date(2022, 1, 1))  # 4.7년 자사
    v2 = S.rule_r05(CTX, data(directorships=[d1, d2]), TODAY)
    assert v2.result == C.SCREEN_FAIL
    assert "계열 합산" in v2.reason


def test_r05_missing_start_date_is_warn():
    d = dirship("자사홀딩스", appointed=None)
    assert S.rule_r05(CTX, data(directorships=[d]), TODAY).result == C.SCREEN_WARN


# ------------------------------------------------------------------ R-06

def test_r06_verified_confirmed_sanction_fails():
    v = S.rule_r06(CTX, data(reputations=[rep("규제 제재", "확정")]), TODAY)
    assert v.result == C.SCREEN_FAIL


def test_r06_unverified_issue_is_not_reflected():
    """미확인 부정 이슈는 판정에 반영하지 않는다 (명예훼손 리스크, PRD F-03 (5))."""
    v = S.rule_r06(CTX, data(reputations=[rep("규제 제재", "확정", verified=False)]), TODAY)
    assert v.result == C.SCREEN_PASS
    assert "미확인" in v.reason


def test_r06_ongoing_is_warn_and_cleared_passes():
    assert S.rule_r06(CTX, data(reputations=[rep("법적 분쟁", "진행중")]), TODAY).result == C.SCREEN_WARN
    assert S.rule_r06(CTX, data(reputations=[rep("규제 제재", "무혐의")]), TODAY).result == C.SCREEN_PASS


def test_r06_confirmed_but_non_disqualifying_category_is_warn():
    assert S.rule_r06(CTX, data(reputations=[rep("윤리 이슈", "확정")]), TODAY).result == C.SCREEN_WARN


def test_r06_positive_reputation_ignored():
    assert S.rule_r06(CTX, data(reputations=[rep("수상", None, polarity="긍정")]), TODAY).result == C.SCREEN_PASS


# ------------------------------------------------------------------ R-07 / R-08 (참고)

def test_r07_is_info_with_grounds():
    v = S.rule_r07(CTX, data(certifications=["공인회계사"], expertise_codes=["EXP_FIN_02"]), TODAY)
    assert v.result == C.SCREEN_INFO
    assert "공인회계사" in v.reason


def test_r07_no_grounds_is_still_info():
    assert S.rule_r07(CTX, data(), TODAY).result == C.SCREEN_INFO


@pytest.mark.parametrize("gender,word", [("M", "경고"), ("F", "기여"), (None, "성별 정보 없음")])
def test_r08_diversity(gender, word):
    v = S.rule_r08(CTX, data(gender=gender), TODAY)
    assert v.result == C.SCREEN_INFO
    assert word in v.reason


def test_r08_not_applicable_below_asset_threshold():
    v = S.rule_r08(replace(CTX, total_assets_krw=1_000), data(gender="M"), TODAY)
    assert "기준 미만" in v.reason


# ------------------------------------------------------------------ 집계

def test_worst_ignores_info():
    assert S.worst([C.SCREEN_INFO, C.SCREEN_INFO]) == C.SCREEN_PASS
    assert S.worst([C.SCREEN_INFO, C.SCREEN_WARN, C.SCREEN_PASS]) == C.SCREEN_WARN
    assert S.worst([C.SCREEN_FAIL, C.SCREEN_WARN]) == C.SCREEN_FAIL


def test_evaluate_input_covers_all_rules():
    verdicts = S.evaluate_input(data(), CTX, TODAY)
    assert [v.rule_id for v in verdicts] == [f"R-0{i}" for i in range(1, 9)]
    assert all(v.reason for v in verdicts), "모든 판정에는 사유가 있어야 한다"


# ------------------------------------------------------------------ DB 연동

def _first_person_id() -> int:
    with session_scope() as s:
        return s.execute(select(Person.person_id).order_by(Person.person_id)).scalars().first()


def test_org_context_reads_settings():
    before = settings.get_raw(C.SET_CONCURRENT_LIMIT)
    try:
        settings.set_value(C.SET_CONCURRENT_LIMIT, "5")
        assert S.OrgContext.load().concurrent_limit == 5
    finally:
        settings.set_value(C.SET_CONCURRENT_LIMIT, before)


def test_evaluate_and_store_preserves_override():
    pid = _first_person_id()
    S.evaluate_and_store(pid)
    S.set_override(pid, "R-03", C.SCREEN_PASS, "법무 검토 결과 거래 관계 없음 확인")
    S.evaluate_and_store(pid)
    with session_scope() as s:
        rows = {r.rule_id: r for r in s.execute(
            select(ScreeningResult).where(ScreeningResult.person_id == pid)).scalars()}
    assert set(rows) == {rid for rid, _ in S.RULES}
    assert rows["R-03"].reviewer_override == C.SCREEN_PASS
    assert rows["R-03"].override_reason
    S.set_override(pid, "R-03", None, None)


def test_override_requires_reason():
    pid = _first_person_id()
    S.evaluate_and_store(pid)
    with pytest.raises(ValueError):
        S.set_override(pid, "R-01", C.SCREEN_PASS, "  ")


def test_override_takes_precedence_in_status():
    pid = _first_person_id()
    S.evaluate_and_store(pid)
    S.set_override(pid, "R-04", C.SCREEN_FAIL, "테스트용 수기 결격 판정")
    try:
        assert S.status_of(pid) == C.SCREEN_FAIL
    finally:
        S.set_override(pid, "R-04", None, None)
