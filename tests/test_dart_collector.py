"""DART 실제 수집기 테스트 (PRD F-05, 소스 등급 A).

DART_API_KEY 가 없어 실제 API 를 호출할 수 없으므로, DART 개발가이드에서 확인한 실제
응답 스키마(status/message/rcept_no/corp_cls/nm/birth_ym/ofcps/rgist_exctv_at/fte_at/
chrg_job/main_career/hffc_pd/tenure_end_on)를 그대로 흉내 낸 값으로 파싱·적재 로직을
검증한다. requests.get 은 전부 monkeypatch 로 대체해 네트워크를 타지 않는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from collectors import dart
from collectors.base import BlockedSourceError
from collectors.dart import DartApiError, DartCollector
from collectors.pipeline import (
    collect_configured_dart_targets,
    ingest_dart_executives,
    parse_target_companies,
)
from core import constants as C
from core import ingest, settings
from data.models import Person, Position
from data.session import session_scope


def _sample_row(**overrides) -> dict:
    row = {
        "rcept_no": "20260311000123",
        "corp_cls": "Y",
        "nm": "홍길동",
        "birth_ym": "1968년 05월",
        "ofcps": "사외이사",
        "rgist_exctv_at": "등기임원",
        "fte_at": "비상근",
        "chrg_job": "감사위원회 위원",
        "main_career": "전 금융감독원 국장",
        "hffc_pd": "2023.03 ~ 현재",
        "tenure_end_on": "2026-03-27",
    }
    row.update(overrides)
    return row


# ------------------------------------------------------------------ 순수 파서

def test_parse_birth_year_extracts_year_from_documented_format():
    assert dart.parse_birth_year("1968년 05월") == 1968


def test_parse_birth_year_tolerates_unexpected_format():
    assert dart.parse_birth_year("1968-05") == 1968
    assert dart.parse_birth_year("") is None
    assert dart.parse_birth_year(None) is None
    assert dart.parse_birth_year("정보없음") is None


def test_parse_dart_date_handles_dash_and_compact_formats():
    from datetime import date

    assert dart.parse_dart_date("2026-03-27") == date(2026, 3, 27)
    assert dart.parse_dart_date("20260327") == date(2026, 3, 27)
    assert dart.parse_dart_date("") is None
    assert dart.parse_dart_date(None) is None
    assert dart.parse_dart_date("모름") is None


def test_classify_role_level_keywords():
    assert dart.classify_role_level("대표이사") == "L1"
    assert dart.classify_role_level("부사장") == "L2"
    assert dart.classify_role_level("상무") == "L3"
    assert dart.classify_role_level("수석연구위원") == "L4"


def test_classify_role_level_board_role_is_not_ranked():
    """사외이사·감사위원은 조직 서열이 아니므로 분류하지 않는다(오분류 방지)."""
    assert dart.classify_role_level("사외이사") is None
    assert dart.classify_role_level("감사위원") is None
    assert dart.classify_role_level(None) is None
    assert dart.classify_role_level("알수없는직위") is None


def test_is_registered_distinguishes_from_unregistered():
    assert dart.is_registered("등기임원") is True
    assert dart.is_registered("미등기임원") is False
    assert dart.is_registered(None) is False


def test_is_full_time_only_matches_exact_label():
    assert dart.is_full_time("상근") is True
    assert dart.is_full_time("비상근") is False


def test_document_url_falls_back_when_no_rcept_no():
    assert dart.document_url("20260311000123") == "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260311000123"
    assert dart.document_url(None) == "https://dart.fss.or.kr/"


def test_row_to_fact_builds_valid_collected_fact_with_source_tier_a():
    fact = dart.row_to_fact(_sample_row(), "가상전자")
    assert fact.source_tier == C.SOURCE_TIER_A
    assert "홍길동" in fact.quote_snippet
    assert "가상전자" in fact.doc_title
    assert fact.url.startswith("https://dart.fss.or.kr/")
    assert fact.payload["nm"] == "홍길동"


def test_row_to_fact_still_blocks_disallowed_domains_via_collected_fact_guard():
    """CollectedFact 자체의 화이트리스트 가드는 dart.py 가 우회하지 않는다(회귀 방지)."""
    from collectors.base import CollectedFact

    with pytest.raises(BlockedSourceError):
        CollectedFact(
            publisher="x", doc_title="x", url="https://blog.naver.com/x",
            source_tier=C.SOURCE_TIER_A, quote_snippet="x",
        )


# ------------------------------------------------------------------ DartCollector (requests mock)

class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_fetch_executives_parses_successful_response(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse({"status": "000", "message": "정상", "list": [_sample_row()]})

    monkeypatch.setattr(dart.requests, "get", fake_get)
    rows = DartCollector().fetch_executives("00126380", "2025", dart.REPRT_CODE_ANNUAL)
    assert len(rows) == 1
    assert rows[0]["nm"] == "홍길동"
    assert captured["url"] == f"{dart.API_BASE}/exctvSttus.json"
    assert captured["params"]["crtfc_key"] == "test-key"
    assert captured["params"]["corp_code"] == "00126380"
    assert captured["params"]["bsns_year"] == "2025"


def test_fetch_executives_raises_on_error_status(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(
        dart.requests, "get",
        lambda *a, **k: _FakeResponse({"status": "013", "message": "조회된 데이터가 없습니다."}),
    )
    with pytest.raises(DartApiError, match="013"):
        DartCollector().fetch_executives("00126380", "2025")


def test_collect_returns_empty_in_dummy_mode(monkeypatch):
    monkeypatch.delenv("DATA_MODE", raising=False)  # 기본값 dummy
    assert DartCollector().collect(corp_code="00126380", bsns_year="2025") == []


def test_collect_requires_api_key_in_live_mode(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.delenv("DART_API_KEY", raising=False)
    try:
        with pytest.raises(RuntimeError, match="DART_API_KEY"):
            DartCollector().collect(corp_code="00126380", bsns_year="2025")
    finally:
        monkeypatch.setenv("DATA_MODE", "dummy")


# ------------------------------------------------------------------ pipeline (적재 연동)

def test_parse_target_companies_skips_malformed_entries():
    parsed = parse_target_companies(["00126380:가상전자", "malformed", "  ", "00164742 : 가상화학  "])
    assert parsed == [("00126380", "가상전자"), ("00164742", "가상화학")]


def test_ingest_dart_executives_creates_person_and_position(monkeypatch):
    monkeypatch.setattr(
        DartCollector, "fetch_executives",
        lambda self, corp_code, bsns_year, reprt_code=dart.REPRT_CODE_ANNUAL: [_sample_row(nm="파이프라인테스트001")],
    )
    stats = ingest_dart_executives("00126380", "가상파이프라인전자", "2025")
    assert stats["rows"] == 1
    assert stats["created_person"] == 1
    assert stats["facts_created"] == 1

    with session_scope() as s:
        person = s.execute(select(Person).where(Person.name_ko == "파이프라인테스트001")).scalar_one()
        assert person.birth_year == 1968
        pos = s.execute(select(Position).where(Position.person_id == person.person_id)).scalar_one()
        assert pos.org_name == "가상파이프라인전자"
        assert pos.title == "사외이사"
        assert pos.role_level is None  # 사외이사는 서열 미분류
        assert pos.is_registered_officer is True
        assert pos.is_full_time is False
        assert pos.term_end_date is not None
        assert pos.is_current is True
        assert pos.source_id is not None


def test_ingest_dart_executives_skips_row_without_name(monkeypatch):
    monkeypatch.setattr(
        DartCollector, "fetch_executives",
        lambda self, corp_code, bsns_year, reprt_code=dart.REPRT_CODE_ANNUAL: [_sample_row(nm="")],
    )
    stats = ingest_dart_executives("00126380", "가상빈이름전자", "2025")
    assert stats["skipped"] == 1
    assert stats["created_person"] == 0


def test_collect_configured_dart_targets_requires_setting(monkeypatch):
    before = settings.get_str(C.SET_DART_TARGET_COMPANIES, default="")
    settings.set_value(C.SET_DART_TARGET_COMPANIES, "")
    try:
        with pytest.raises(ValueError, match="dart_target_companies"):
            collect_configured_dart_targets("2025")
    finally:
        settings.set_value(C.SET_DART_TARGET_COMPANIES, before)


def test_collect_configured_dart_targets_aggregates_across_companies(monkeypatch):
    calls: list[str] = []

    def fake_fetch(self, corp_code, bsns_year, reprt_code=dart.REPRT_CODE_ANNUAL):
        calls.append(corp_code)
        return [_sample_row(nm=f"대상{corp_code}")]

    monkeypatch.setattr(DartCollector, "fetch_executives", fake_fetch)
    before = settings.get_str(C.SET_DART_TARGET_COMPANIES, default="")
    settings.set_value(C.SET_DART_TARGET_COMPANIES, "00111111:가상A,00222222:가상B")
    try:
        total = collect_configured_dart_targets("2025")
        assert calls == ["00111111", "00222222"]
        assert total["rows"] == 2
        assert total["created_person"] == 2
    finally:
        settings.set_value(C.SET_DART_TARGET_COMPANIES, before)


# ------------------------------------------------------------------ batch.run.collect() 연동

def test_batch_collect_uses_dart_pipeline_in_live_mode(monkeypatch):
    from batch import run as batch

    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.setattr(
        DartCollector, "fetch_executives",
        lambda self, corp_code, bsns_year, reprt_code=dart.REPRT_CODE_ANNUAL: [_sample_row(nm="배치연동테스트001")],
    )
    before = settings.get_str(C.SET_DART_TARGET_COMPANIES, default="")
    settings.set_value(C.SET_DART_TARGET_COMPANIES, "00133333:가상배치전자")
    try:
        result = batch.collect()
        assert result["dart"]["created_person"] == 1
    finally:
        settings.set_value(C.SET_DART_TARGET_COMPANIES, before)
        monkeypatch.setenv("DATA_MODE", "dummy")
