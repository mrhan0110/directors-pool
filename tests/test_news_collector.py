"""네이버 뉴스검색 수집기 테스트 (PRD F-05, 소스 등급 C, §5.2 명예훼손 리스크 관리).

NAVER_CLIENT_ID/SECRET 이 없어 실제 API 를 호출할 수 없으므로, 공식 스펙(응답
{lastBuildDate,total,start,display,items:[{title,originallink,link,description,pubDate}]})을
그대로 흉내 낸 값으로 파싱·적재 로직을 검증한다. requests.get 은 monkeypatch 로 대체한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from collectors import news
from collectors.news import NaverNewsApiError, NewsCollector
from collectors.pipeline import ingest_news_for_person
from core import ingest
from data.models import Reputation, Source
from data.session import session_scope


def _sample_item(**overrides) -> dict:
    item = {
        "title": "<b>가상001</b> 대표, 신사업 진출 논란",
        "originallink": "https://news.example.com/article/000001",
        "link": "https://n.news.naver.com/article/000/0000001",
        "description": "<b>가상001</b> 대표가 신사업 진출을 두고 논란에 휩싸였다.",
        "pubDate": "Mon, 22 Sep 2026 09:00:00 +0900",
    }
    item.update(overrides)
    return item


# ------------------------------------------------------------------ 순수 파서

def test_strip_tags_removes_bold_and_unescapes_entities():
    assert news.strip_tags("<b>가상001</b> &amp; 대표") == "가상001 & 대표"
    assert news.strip_tags(None) == ""


def test_parse_pub_date_handles_rfc822_format():
    from datetime import date

    assert news.parse_pub_date("Mon, 22 Sep 2026 09:00:00 +0900") == date(2026, 9, 22)
    assert news.parse_pub_date(None) is None
    assert news.parse_pub_date("이상한 형식") is None


def test_classify_polarity_is_conservative():
    assert news.classify_polarity("검찰, 혐의로 기소") == "부정"
    assert news.classify_polarity("사업 확장 발표") == "중립"
    assert news.classify_polarity("") == "중립"


def test_item_to_fact_builds_valid_collected_fact():
    fact = news.item_to_fact(_sample_item(), "가상001")
    assert fact.source_tier == news.SOURCE_TIER_C
    assert "가상001" in fact.doc_title
    assert fact.doc_title.count("<b>") == 0
    assert fact.url == "https://news.example.com/article/000001"
    assert fact.published_date == "2026-09-22"


def test_item_to_fact_falls_back_to_naver_link_when_no_originallink():
    fact = news.item_to_fact(_sample_item(originallink=""), "가상001")
    assert fact.url == "https://n.news.naver.com/article/000/0000001"


# ------------------------------------------------------------------ NewsCollector (requests mock)

class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def test_search_parses_successful_response(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _FakeResponse({"total": 1, "items": [_sample_item()]})

    monkeypatch.setattr(news.requests, "get", fake_get)
    items = NewsCollector().search("가상001", display=5, sort="date")
    assert len(items) == 1
    assert captured["url"] == news.API_URL
    assert captured["headers"]["X-Naver-Client-Id"] == "id"
    assert captured["headers"]["X-Naver-Client-Secret"] == "secret"
    assert captured["params"]["query"] == "가상001"
    assert captured["params"]["display"] == 5


def test_search_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    monkeypatch.setattr(news.requests, "get", lambda *a, **k: _FakeResponse({}, status_code=401, text="인증 실패"))
    with pytest.raises(NaverNewsApiError, match="401"):
        NewsCollector().search("가상001")


def test_collect_returns_empty_in_dummy_mode(monkeypatch):
    monkeypatch.delenv("DATA_MODE", raising=False)
    assert NewsCollector().collect(person_name="가상001") == []


def test_collect_requires_credentials_in_live_mode(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    try:
        with pytest.raises(RuntimeError, match="NAVER_CLIENT_ID"):
            NewsCollector().collect(person_name="가상001")
    finally:
        monkeypatch.setenv("DATA_MODE", "dummy")


def test_collect_appends_context_to_query(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["query"] = params["query"]
        return _FakeResponse({"items": []})

    monkeypatch.setattr(news.requests, "get", fake_get)
    try:
        NewsCollector().collect(person_name="가상001", context="가상전자")
        assert captured["query"] == "가상001 가상전자"
    finally:
        monkeypatch.setenv("DATA_MODE", "dummy")


# ------------------------------------------------------------------ pipeline (평판 적재)

def test_ingest_news_for_person_creates_unverified_reputation(monkeypatch):
    monkeypatch.setattr(
        NewsCollector, "search",
        lambda self, query, display=20, start=1, sort="date": [_sample_item(nm="뉴스적재테스트")],
    )
    res = ingest.get_or_create_person("뉴스적재테스트001", birth_year=1970)
    assert res.status == "created"

    stats = ingest_news_for_person(res.person_id, "뉴스적재테스트001")
    assert stats["created"] == 1

    with session_scope() as s:
        rep = s.execute(select(Reputation).where(Reputation.person_id == res.person_id)).scalar_one()
        assert rep.verified_yn is False
        assert rep.polarity in ("긍정", "중립", "부정")
        assert rep.category == "언론 보도"
        src = s.get(Source, rep.source_id)
        assert src.source_tier == news.SOURCE_TIER_C
        assert src.url == "https://news.example.com/article/000001"


def test_ingest_news_for_person_skips_duplicate_url_on_rerun(monkeypatch):
    monkeypatch.setattr(
        NewsCollector, "search",
        lambda self, query, display=20, start=1, sort="date": [_sample_item()],
    )
    res = ingest.get_or_create_person("뉴스중복테스트001", birth_year=1971)
    first = ingest_news_for_person(res.person_id, "뉴스중복테스트001")
    second = ingest_news_for_person(res.person_id, "뉴스중복테스트001")
    assert first["created"] == 1
    assert second["created"] == 0
    assert second["skipped_duplicate"] == 1

    with session_scope() as s:
        count = len(list(s.execute(
            select(Reputation).where(Reputation.person_id == res.person_id)
        ).scalars()))
    assert count == 1


def test_ingest_news_for_person_skips_items_without_url(monkeypatch):
    monkeypatch.setattr(
        NewsCollector, "search",
        lambda self, query, display=20, start=1, sort="date": [_sample_item(originallink="", link="")],
    )
    res = ingest.get_or_create_person("뉴스빈링크테스트001", birth_year=1972)
    stats = ingest_news_for_person(res.person_id, "뉴스빈링크테스트001")
    assert stats["created"] == 0
    assert stats["skipped_invalid"] == 1
