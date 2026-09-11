"""불변 규칙 테스트.

여기가 깨지면 기능이 아니라 원칙이 깨진 것이다. (CLAUDE.md 불변 규칙 1·2·3·7)
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from collectors.base import BlockedSourceError, CollectedFact, assert_source_allowed
from core import codes as CODES
from core import constants as C
from core import expertise as EXP
from data.models import Expertise, Position, Reputation, Source
from data.session import session_scope


def _source(session) -> Source:
    src = Source(
        publisher="금융감독원 전자공시시스템",
        doc_title="테스트 문서",
        url="https://dart.example.com/test",
        source_tier=C.SOURCE_TIER_A,
        quote_snippet="인용",
    )
    session.add(src)
    session.flush()
    return src


# ------------------------------------------------------------------ 규칙 1: 출처 없는 값 금지

def test_position_requires_source():
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            s.add(Position(person_id=999, org_name="가상", title="상무", source_id=None))


def test_reputation_requires_source():
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            s.add(Reputation(person_id=999, polarity="부정", summary="요약", source_id=None))


def test_expertise_requires_source_and_snippet():
    with pytest.raises(IntegrityError):
        with session_scope() as s:
            s.add(
                Expertise(
                    person_id=999,
                    taxonomy_code="EXP_FIN_01",
                    level="중",
                    confidence="중",
                    evidence_snippet=None,
                    source_id=None,
                )
            )


# ------------------------------------------------------------------ 규칙 2: 근거 없는 전문분야 금지

def test_build_rejects_blank_evidence():
    with pytest.raises(EXP.MissingEvidenceError):
        EXP.build(person_id=1, taxonomy_code="EXP_FIN_01", evidence_snippet="   ", source_id=1)


def test_build_rejects_missing_source():
    with pytest.raises(EXP.MissingEvidenceError):
        EXP.build(person_id=1, taxonomy_code="EXP_FIN_01", evidence_snippet="근거", source_id=0)


def test_build_rejects_unknown_taxonomy_code():
    with pytest.raises(ValueError):
        EXP.build(person_id=1, taxonomy_code="자유롭게 입력한 전문분야", evidence_snippet="근거", source_id=1)


def test_build_accepts_valid_input():
    with session_scope() as s:
        src = _source(s)
        item = EXP.build(
            person_id=1,
            taxonomy_code="EXP_FIN_01",
            evidence_snippet="재무전략 담당 경력 확인",
            source_id=src.source_id,
        )
    assert item.taxonomy_code == "EXP_FIN_01"


# ------------------------------------------------------------------ 규칙 3: 드롭다운 코드는 DB 에서

def test_all_filter_categories_are_seeded():
    required = [
        C.CODE_GENDER,
        C.CODE_AGE_BAND,
        C.CODE_JOB_SCOPE,
        C.CODE_JOB_L1,
        C.CODE_JOB_L2,
        C.CODE_ROLE_LEVEL,
        C.CODE_EXPERTISE_L1,
        C.CODE_EXPERTISE_L2,
        C.CODE_INDUSTRY,
        C.CODE_NATIONALITY,
        C.CODE_CONCURRENT,
        C.CODE_TERM_REMAIN,
        C.CODE_SCREENING,
        C.CODE_REPUTATION,
        C.CODE_REGION,
        C.CODE_FRESHNESS,
        C.CODE_SORT,
        C.CODE_RESULT_LIMIT,
    ]
    for category in required:
        assert CODES.load_codes(category), f"{category} 코드가 시드되지 않았습니다"


def test_expertise_taxonomy_children_have_valid_parents():
    l1 = set(CODES.code_map(C.CODE_EXPERTISE_L1))
    for item in CODES.load_codes(C.CODE_EXPERTISE_L2):
        assert item.parent_code in l1


def test_job_l2_children_have_valid_parents():
    l1 = set(CODES.code_map(C.CODE_JOB_L1))
    for item in CODES.load_codes(C.CODE_JOB_L2):
        assert item.parent_code in l1


# ------------------------------------------------------------------ 규칙 7: 소스 화이트리스트

@pytest.mark.parametrize(
    "url",
    [
        "https://blog.naver.com/someone/123",
        "https://cafe.naver.com/board/1",
        "https://namu.wiki/w/somebody",
        "https://ko.wikipedia.org/wiki/somebody",
        "https://twitter.com/someone/status/1",
        "https://www.teamblind.com/post/x",
    ],
)
def test_blocked_domains_are_rejected(url):
    with pytest.raises(BlockedSourceError):
        assert_source_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://dart.fss.or.kr/dsab001/main.do",
        "https://kind.krx.co.kr/",
        "https://company.example.com/about",
    ],
)
def test_allowed_domains_pass(url):
    assert_source_allowed(url)


def test_collected_fact_requires_quote_snippet():
    with pytest.raises(ValueError):
        CollectedFact(
            publisher="가상일보",
            doc_title="제목",
            url="https://news.example.com/1",
            source_tier=C.SOURCE_TIER_C,
            quote_snippet="",
        )
