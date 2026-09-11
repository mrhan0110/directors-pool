"""적합도 점수 테스트 (PRD F-06, 인수 기준 #7·#15)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select

from core import constants as C
from core import scoring as SC
from core import screening, search, settings
from data.models import Expertise
from data.session import session_scope

CTX = SC.ScoreContext(
    weights=SC.Weights(expertise=40, skill_gap=20, career=15, availability=15, risk=10),
    skill_gaps=("EXP_SEC_01", "EXP_ESG_01"),
    concurrent_limit=2,
    attendance_warn_rate=0.75,
    own_orgs=("자사홀딩스",),
)


def d(company="타사", *, listed=True, current=True, rate=None):
    return NS(company_name=company, listed_yn=listed, is_current=current, board_attendance_rate=rate)


def inp(**kw):
    return SC.ScoreInput(**kw)


def test_default_weights_sum_to_100():
    w = SC.Weights.load()
    assert w.expertise + w.skill_gap + w.career + w.availability + w.risk == 100


def test_weights_come_from_settings():
    before = settings.get_raw(C.SET_W_CAREER)
    try:
        settings.set_value(C.SET_W_CAREER, "30")
        assert SC.Weights.load().career == 30
    finally:
        settings.set_value(C.SET_W_CAREER, before)


@pytest.mark.parametrize(
    "expertise,expected",
    [
        ([("EXP_SEC_01", True), ("EXP_ESG_01", True)], 20),
        ([("EXP_SEC_01", True)], 10),
        ([("EXP_SEC_01", False)], 5),
        ([("EXP_FIN_01", True)], 0),
    ],
)
def test_skill_gap(expertise, expected):
    assert SC.skill_gap_component(inp(expertise=expertise), CTX)[0] == expected


def test_skill_gap_without_configured_gaps():
    pts, reason = SC.skill_gap_component(inp(expertise=[("EXP_SEC_01", True)]), replace(CTX, skill_gaps=()))
    assert pts == 0 and "미설정" in reason


@pytest.mark.parametrize("levels,expected", [(["L3", "L1"], 15), (["L3"], 7.5), ([None], 0)])
def test_career(levels, expected):
    positions = [NS(role_level=lv) for lv in levels]
    assert SC.career_component(inp(positions=positions), CTX)[0] == expected


@pytest.mark.parametrize("n,expected", [(0, 15), (1, 7.5), (2, 0), (3, 0)])
def test_availability_by_concurrent_count(n, expected):
    dirs = [d(f"타사{i}") for i in range(n)]
    assert SC.availability_component(inp(directorships=dirs), CTX)[0] == expected


def test_availability_ignores_own_unlisted_and_ended():
    dirs = [d("자사홀딩스"), d("비상장", listed=False), d("종료", current=False)]
    assert SC.availability_component(inp(directorships=dirs), CTX)[0] == 15


def test_low_attendance_halves_availability():
    pts, reason = SC.availability_component(inp(directorships=[d(rate=0.6)]), CTX)
    assert pts == 3.75
    assert "감점" in reason


@pytest.mark.parametrize(
    "results,expected",
    [
        ([C.SCREEN_FAIL, C.SCREEN_WARN], 10),
        ([C.SCREEN_WARN], 5),
        ([C.SCREEN_WARN] * 3, 10),
        ([C.SCREEN_INFO, C.SCREEN_PASS], 0),
    ],
)
def test_risk(results, expected):
    assert SC.risk_component(inp(screening_results=results), CTX)[0] == expected


def test_base_score_is_sum_of_components():
    data = inp(
        expertise=[("EXP_SEC_01", True)],
        positions=[NS(role_level="L2")],
        directorships=[d()],
        screening_results=[C.SCREEN_WARN],
    )
    total, bd = SC.base_score(data, CTX)
    assert total == pytest.approx(10 + 11.25 + 7.5 - 5)
    assert bd["risk"]["points"] == -5
    assert all(bd[k]["reason"] for k in ("skill_gap", "career", "availability", "risk"))


# ------------------------------------------------------------------ DB: 검색 정렬 연동

@pytest.fixture(scope="module")
def scored():
    screening.evaluate_all()
    SC.score_all()


def test_fit_sort_is_descending_and_fail_last(scored):
    result = search.search({"sort": "FIT"}, "NALL", C.ROLE_STAFF)
    ranks = [1 if r.screening == C.SCREEN_FAIL else 0 for r in result.rows]
    assert ranks == sorted(ranks), "결격 후보가 목록 중간에 섞여 있음"
    normal = [r.fit_score for r in result.rows if r.screening != C.SCREEN_FAIL]
    assert normal == sorted(normal, reverse=True)
    assert all(r.fit_score is not None and r.fit_basis for r in result.rows)


def test_expertise_match_adds_weight(scored):
    with session_scope() as s:
        code = s.execute(
            select(Expertise.taxonomy_code).group_by(Expertise.taxonomy_code)
            .order_by(func.count().desc())
        ).scalars().first()
    w = SC.Weights.load().expertise
    result = search.search({"expertise_l2": [code], "sort": "FIT"}, "NALL", C.ROLE_STAFF)
    assert result.rows
    for r in result.rows:
        base = SC.fit_score(r.person_id)
        assert r.fit_score == pytest.approx(base + w, abs=0.11)
        assert "전문분야 매칭" in r.fit_basis


def test_no_expertise_condition_means_zero_match(scored):
    result = search.search({"sort": "FIT"}, "N10", C.ROLE_STAFF)
    for r in result.rows:
        assert r.fit_score == pytest.approx(SC.fit_score(r.person_id), abs=0.11)


def test_display_clamps_and_marks_missing():
    assert SC.display(None) == SC.NOT_COMPUTED_LABEL
    assert SC.display(-3) == "0"
    assert SC.display(104.6) == "100"
