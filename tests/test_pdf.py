"""사추위 보고용 PDF 테스트 (PRD 부록 A·B, F-08-1, F-09-12, 인수 기준 #8)."""

from __future__ import annotations

import re
from datetime import date, datetime

import pytest
from reportlab.platypus import Paragraph, Table

from core import constants as C
from core import expertise as EXP
from core import pools
from data.models import Achievement, Person, Position, Reputation, Source
from data.repository import get_person_detail
from data.session import session_scope
from reports import pdf as PDF
from reports.builder import ExportBlockedError, _candidate_doc, build_candidate_pdf, build_pool_pdf

VIEWER = "가상 담당자 (staff@example.com)"


def _make_person(status: str) -> int:
    with session_scope() as s:
        a = Source(publisher="금융감독원 전자공시시스템", doc_title="PDF 테스트 보고서",
                   url="https://dart.example.com/pdf-a", source_tier=C.SOURCE_TIER_A, quote_snippet="인용",
                   published_date=date(2026, 3, 18))
        c = Source(publisher="가상일보", doc_title="PDF 테스트 기사", url="https://news.example.com/pdf-c",
                   source_tier=C.SOURCE_TIER_C, quote_snippet="인용", published_date=date(2026, 1, 5))
        p = Person(name_ko="가상PDF 테스트", name_en="TEST-PDF", gender="F", birth_year=1965,
                   nationality=["KR"], profile_status=status)
        s.add_all([a, c, p])
        s.flush()
        s.add(Position(person_id=p.person_id, org_name="가상전자", title="부사장", role_level="L2",
                       is_current=True, start_date=date(2021, 1, 1), duties="재무전략 총괄", source_id=a.source_id))
        s.add(Achievement(person_id=p.person_id, category="경영 성과", description="흑자전환 주도",
                          quantitative_metric="영업이익률 4%→9%", period="2021~2024", source_id=a.source_id))
        s.add(Reputation(person_id=p.person_id, polarity="긍정", category="수상·포상", summary="산업포장 수상",
                         verified_yn=True, source_id=c.source_id))
        s.add(Reputation(person_id=p.person_id, polarity="부정", category="윤리 이슈", summary="미확인 의혹 보도",
                         verified_yn=False, source_id=c.source_id))
        s.add(EXP.build(p.person_id, "EXP_FIN_01", "재무전략 총괄", a.source_id, is_primary=True))
        return p.person_id


def _texts(story) -> list[str]:
    out = []
    for f in story:
        if isinstance(f, Paragraph):
            out.append(f.text)
        elif isinstance(f, Table):
            out += [cell.text for row in f._cellvalues for cell in row if isinstance(cell, Paragraph)]
    return out


def _pages(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", data))


def test_reviewed_profile_renders_two_or_three_pages():
    pid = _make_person(C.PROFILE_REVIEWED)
    data = build_candidate_pdf(pid, C.ROLE_STAFF, VIEWER, opinion="감사위원 적임", legal_review="결격 사유 없음")
    assert data.startswith(b"%PDF")
    assert 2 <= _pages(data) <= 3


def test_unreviewed_profile_is_blocked():
    pid = _make_person(C.PROFILE_UNREVIEWED)
    with pytest.raises(ExportBlockedError):
        build_candidate_pdf(pid, C.ROLE_STAFF, VIEWER)


def test_viewer_cannot_export_even_reviewed():
    pid = _make_person(C.PROFILE_REVIEWED)
    with pytest.raises(ExportBlockedError):
        build_candidate_pdf(pid, C.ROLE_VIEWER, VIEWER)


def test_story_has_footnotes_for_every_source_and_excludes_unverified():
    pid = _make_person(C.PROFILE_REVIEWED)
    story, notes = PDF.candidate_story(_candidate_doc(pid), PDF._styles())
    texts = "\n".join(_texts(story))
    urls = {s.url for s in notes.sources}
    assert {"https://dart.example.com/pdf-a", "https://news.example.com/pdf-c"} <= urls
    for i, _ in enumerate(notes.sources, start=1):
        assert f"[{i}]" in texts
    assert "산업포장 수상" in texts
    assert "미확인 의혹 보도" not in texts, "미확인 평판이 보고서에 수록됨"
    assert "미확인 보도 1건은 수록하지 않았습니다" in texts
    assert "재무전략" in texts  # 근거 있는 전문분야


def test_pool_pdf_requires_all_members_reviewed():
    ok = _make_person(C.PROFILE_REVIEWED)
    bad = _make_person(C.PROFILE_UNREVIEWED)
    pool_id = pools.create_pool("PDF 테스트 POOL", user_id=1)
    pools.add_members(pool_id, [ok], user_id=1)
    data = build_pool_pdf(pool_id, C.ROLE_HEAD, VIEWER)
    assert data.startswith(b"%PDF") and _pages(data) >= 3  # 요약표 1면 + 개인 2면
    pools.add_members(pool_id, [bad], user_id=1)
    with pytest.raises(ExportBlockedError):
        build_pool_pdf(pool_id, C.ROLE_HEAD, VIEWER)


def test_stamp_contains_viewer_and_time():
    s = PDF.stamp(VIEWER, datetime(2026, 9, 11, 9, 5))
    assert "staff@example.com" in s and "2026-09-11 09:05" in s and "대외비" in s


def test_font_supports_korean():
    assert PDF.font_name() in ("KR", "HYGothic-Medium")
