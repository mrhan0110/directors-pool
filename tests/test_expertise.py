"""전문분야 자동 분류 테스트 (PRD F-04, §6.4).

가장 중요한 성질: 근거 스니펫(원문 + 출처) 없는 전문분야는 어떤 경로로도 나오지 않는다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from core import codes as CODES
from core import constants as C
from core import expertise as EXP
from core.expertise_rules import JOB_HINTS, KEYWORDS
from data.models import Expertise, Person, Position, Source
from data.session import session_scope

TODAY = date(2026, 9, 11)


def ev(text, *, sid=1, when=TODAY, tier=C.SOURCE_TIER_A, job=None):
    return EXP.Evidence(text=text, source_id=sid, evidence_date=when, tier=tier, job_l2_code=job)


# ------------------------------------------------------------------ 사전 정합성

def test_keyword_codes_exist_in_taxonomy():
    valid = set(CODES.code_map(C.CODE_EXPERTISE_L2))
    assert set(KEYWORDS) <= valid
    assert set(JOB_HINTS.values()) <= valid


# ------------------------------------------------------------------ 매칭·가중

def test_match_codes_finds_keyword_and_job_hint():
    hits = EXP.match_codes("가상전자 재무전략 총괄", "ACCT_TAX")
    assert "EXP_FIN_01" in hits
    assert "EXP_FIN_03" in hits  # 직업 힌트


@pytest.mark.parametrize(
    "when,expected",
    [
        (date(2021, 9, 12), 1.0),   # 5년 이내
        (date(2020, 9, 1), 0.6),    # 6~10년
        (date(2016, 9, 12), 0.6),   # 10년 이내 경계
        (date(2015, 1, 1), 0.3),    # 10년 초과
        (None, 0.3),                # 날짜 미상
    ],
)
def test_recency_weight(when, expected):
    assert EXP.recency_weight(when, TODAY) == expected


def test_tier_weight_applies():
    a = EXP.classify_evidence([ev("회계 공시 담당", tier=C.SOURCE_TIER_A)], TODAY)[0]
    c = EXP.classify_evidence([ev("회계 공시 담당", tier=C.SOURCE_TIER_C)], TODAY)[0]
    assert a.score == pytest.approx(1.0)
    assert c.score == pytest.approx(0.5)


# ------------------------------------------------------------------ 결과 구조

def test_top_three_are_primary():
    evs = [
        ev("재무전략 CFO", sid=1), ev("재무전략 총괄", sid=2),
        ev("M&A 인수합병", sid=3), ev("ESG 지속가능경영", sid=4),
        ev("개인정보 보호", sid=5, when=date(2010, 1, 1)),
    ]
    out = EXP.classify_evidence(evs, TODAY)
    assert sum(1 for c in out if c.is_primary) == 3
    assert out[0].code == "EXP_FIN_01"  # 근거 2건 → 최고점
    assert out[0].evidence_count == 2
    assert out[0].extra_source_ids == [2]
    assert not out[-1].is_primary


def test_confidence_levels():
    high = EXP.classify_evidence([ev("회계", sid=1), ev("결산", sid=2), ev("공시", sid=3)], TODAY)[0]
    low = EXP.classify_evidence([ev("회계", tier=C.SOURCE_TIER_C, when=date(2000, 1, 1))], TODAY)[0]
    assert high.confidence == "상"
    assert low.confidence == "하"


def test_no_evidence_means_no_classification():
    """근거가 없으면 분류가 생기지 않는다 — 환각 차단 (PRD 분류 로직 5)."""
    assert EXP.classify_evidence([], TODAY) == []
    assert EXP.classify_evidence([ev("   "), ev("회계", sid=0)], TODAY) == []
    assert EXP.classify_evidence([ev("관련 키워드 없는 문장")], TODAY) == []


def test_every_classification_has_snippet_and_source():
    out = EXP.classify_evidence([ev("회계 공시 " * 50, sid=7)], TODAY)
    assert out and all(c.snippet.strip() and c.source_id for c in out)
    assert all(len(c.snippet) <= EXP.SNIPPET_MAX for c in out)


# ------------------------------------------------------------------ 출력 가드

def test_displayable_filters_missing_snippet_or_source():
    src = NS(url="https://dart.example.com/1")
    items = [
        NS(evidence_snippet="근거 있음", source_id=1),
        NS(evidence_snippet="  ", source_id=1),
        NS(evidence_snippet="출처 없음", source_id=99),
    ]
    shown = EXP.displayable(items, {1: src})
    assert [i.evidence_snippet for i in shown] == ["근거 있음"]


def test_llm_items_must_quote_real_evidence():
    evs = [ev("가상전자 재무전략 총괄", sid=3)]
    items = [
        {"code": "EXP_FIN_01", "snippet": "재무전략 총괄", "source_id": 3},   # 원문에 존재
        {"code": "EXP_DIG_02", "snippet": "AI 전문가", "source_id": 3},       # 환각
        {"code": "자유텍스트", "snippet": "재무전략", "source_id": 3},          # 택소노미 외
        {"code": "EXP_FIN_01", "snippet": "재무전략", "source_id": 9},         # 다른 출처
    ]
    assert EXP.verify_llm_items(items, evs) == [items[0]]


def test_llm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EXPERTISE_LLM_ENABLED", raising=False)
    assert EXP.llm_enabled() is False


# ------------------------------------------------------------------ DB: 저장·수정 이력

@pytest.fixture
def person_with_evidence():
    """재무·M&A 근거가 명확한 가상 후보 1명을 만든다."""
    with session_scope() as s:
        src = Source(publisher="금융감독원 전자공시시스템", doc_title="테스트 사업보고서",
                     url="https://dart.example.com/exp-test", source_tier=C.SOURCE_TIER_A,
                     quote_snippet="인용")
        person = Person(name_ko="가상테스트 분류", name_en="TEST-EXP", nationality=["KR"])
        s.add_all([src, person])
        s.flush()
        for title, duties in [("CFO", "재무전략 총괄"), ("전무", "M&A 인수합병 추진"), ("상무", "회계 결산")]:
            s.add(Position(person_id=person.person_id, org_name="가상전자", title=title,
                           duties=duties, role_level="L2", is_current=False,
                           start_date=date(2020, 1, 1), end_date=date(2024, 1, 1),
                           source_id=src.source_id))
        pid = person.person_id
    return pid


def _codes(pid):
    with session_scope() as s:
        return {e.taxonomy_code: e for e in s.execute(
            select(Expertise).where(Expertise.person_id == pid)).scalars()}


def test_store_creates_rows_with_evidence(person_with_evidence):
    pid = person_with_evidence
    EXP.store(pid)
    rows = _codes(pid)
    assert {"EXP_FIN_01", "EXP_CAP_01", "EXP_FIN_02"} <= set(rows)
    assert all(r.evidence_snippet.strip() and r.source_id for r in rows.values())
    assert sum(1 for r in rows.values() if r.is_primary) <= EXP.MAX_PRIMARY


def test_confirmed_row_survives_reclassification(person_with_evidence):
    pid = person_with_evidence
    EXP.store(pid)
    EXP.confirm(pid, "EXP_CAP_01", user_id=None)
    with session_scope() as s:
        row = s.execute(select(Expertise).where(
            Expertise.person_id == pid, Expertise.taxonomy_code == "EXP_CAP_01")).scalar_one()
        row.evidence_snippet = "담당자가 확인한 근거 문구"
    EXP.store(pid)
    assert _codes(pid)["EXP_CAP_01"].evidence_snippet == "담당자가 확인한 근거 문구"


def test_user_deleted_code_is_not_readded(person_with_evidence):
    pid = person_with_evidence
    EXP.store(pid)
    with pytest.raises(ValueError):
        EXP.remove(pid, "EXP_FIN_02", user_id=None, reason=" ")
    EXP.remove(pid, "EXP_FIN_02", user_id=None, reason="회계 실무 경력 아님 — 결산 보고만 수령")
    EXP.store(pid)
    assert "EXP_FIN_02" not in _codes(pid)
    actions = [h.action for h in EXP.history_of(pid)]
    assert EXP.ACTION_DELETE in actions


def test_primary_limit_enforced(person_with_evidence):
    pid = person_with_evidence
    EXP.store(pid)
    rows = _codes(pid)
    secondary = [c for c, r in rows.items() if not r.is_primary]
    if sum(1 for r in rows.values() if r.is_primary) == EXP.MAX_PRIMARY and secondary:
        with pytest.raises(ValueError):
            EXP.set_primary(pid, secondary[0], True, user_id=None)
    primary = next(c for c, r in rows.items() if r.is_primary)
    EXP.set_primary(pid, primary, False, user_id=None)
    assert _codes(pid)[primary].is_primary is False
    assert _codes(pid)[primary].manually_edited is True
