"""기업 홈페이지 범용 수집기 테스트 (PRD F-05, 소스 등급 B).

robots.txt 확인(RobotFileParser.read/can_fetch)과 페이지 요청(requests.get)을 전부
monkeypatch 로 대체해 네트워크를 타지 않는다.
"""

from __future__ import annotations

import pytest

from collectors import web
from collectors.base import BlockedSourceError
from collectors.web import FetchError, RobotsDisallowedError, WebCollector

SAMPLE_HTML = """
<html>
<head>
  <title>가상전자 — 경영진 소개</title>
  <meta name="description" content="가상전자의 경영진을 소개합니다.">
</head>
<body>
  <p>홍길동 대표이사는 2020년부터 재직 중입니다.</p>
  <p>주요 경력: 가상금융지주 전무, 가상캐피탈 상무.</p>
  <script>console.log('무시되어야 함');</script>
</body>
</html>
"""


def test_extract_generic_pulls_title_description_and_paragraphs():
    extracted = web.extract_generic(SAMPLE_HTML)
    assert extracted["title"] == "가상전자 — 경영진 소개"
    assert "경영진을 소개" in extracted["description"]
    assert "홍길동" in extracted["body_text"]
    assert "console.log" not in extracted["body_text"]


def test_extract_generic_handles_empty_html():
    extracted = web.extract_generic("<html></html>")
    assert extracted == {"title": "", "description": "", "body_text": ""}


def test_page_to_fact_prefers_description_then_body_then_title():
    fact = web.page_to_fact("https://company.example.com/about", web.extract_generic(SAMPLE_HTML))
    assert fact.quote_snippet.startswith("가상전자의 경영진을 소개합니다")
    assert fact.source_tier == web.SOURCE_TIER_B
    assert fact.publisher == "company.example.com"


def test_page_to_fact_raises_when_nothing_extracted():
    with pytest.raises(FetchError):
        web.page_to_fact("https://company.example.com/empty", {"title": "", "description": "", "body_text": ""})


def test_page_to_fact_blocks_disallowed_domain():
    with pytest.raises(BlockedSourceError):
        web.page_to_fact("https://blog.naver.com/x", {"title": "t", "description": "d", "body_text": ""})


# ------------------------------------------------------------------ can_fetch / fetch_page (네트워크 mock)

class _FakeRobotParser:
    def __init__(self, allow: bool = True, raise_on_read: bool = False):
        self.allow = allow
        self.raise_on_read = raise_on_read

    def set_url(self, url):
        pass

    def read(self):
        if self.raise_on_read:
            raise OSError("robots.txt 를 읽을 수 없음")

    def can_fetch(self, agent, url):
        return self.allow


def test_can_fetch_returns_false_when_robots_unreadable(monkeypatch):
    monkeypatch.setattr(web.robotparser, "RobotFileParser", lambda: _FakeRobotParser(raise_on_read=True))
    assert web.can_fetch("https://company.example.com/about") is False


def test_can_fetch_respects_disallow(monkeypatch):
    monkeypatch.setattr(web.robotparser, "RobotFileParser", lambda: _FakeRobotParser(allow=False))
    assert web.can_fetch("https://company.example.com/about") is False


def test_can_fetch_allows_when_permitted(monkeypatch):
    monkeypatch.setattr(web.robotparser, "RobotFileParser", lambda: _FakeRobotParser(allow=True))
    assert web.can_fetch("https://company.example.com/about") is True


class _FakeHttpResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_page_blocked_by_robots(monkeypatch):
    monkeypatch.setattr(web, "can_fetch", lambda url, user_agent=web.USER_AGENT: False)
    with pytest.raises(RobotsDisallowedError):
        web.fetch_page("https://company.example.com/about")


def test_fetch_page_returns_html_when_allowed(monkeypatch):
    monkeypatch.setattr(web, "can_fetch", lambda url, user_agent=web.USER_AGENT: True)
    monkeypatch.setattr(web.requests, "get", lambda url, headers=None, timeout=None: _FakeHttpResponse(SAMPLE_HTML))
    assert "가상전자" in web.fetch_page("https://company.example.com/about")


def test_collector_collect_returns_empty_in_dummy_mode(monkeypatch):
    monkeypatch.delenv("DATA_MODE", raising=False)
    assert WebCollector().collect(url="https://company.example.com/about") == []


def test_collector_collect_requires_url_in_live_mode(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    try:
        with pytest.raises(ValueError, match="url"):
            WebCollector().collect()
    finally:
        monkeypatch.setenv("DATA_MODE", "dummy")


def test_collector_collect_builds_fact_end_to_end(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.setattr(web, "can_fetch", lambda url, user_agent=web.USER_AGENT: True)
    monkeypatch.setattr(web.requests, "get", lambda url, headers=None, timeout=None: _FakeHttpResponse(SAMPLE_HTML))
    try:
        facts = WebCollector().collect(url="https://company.example.com/about")
        assert len(facts) == 1
        assert facts[0].source_tier == web.SOURCE_TIER_B
        assert facts[0].url == "https://company.example.com/about"
    finally:
        monkeypatch.setenv("DATA_MODE", "dummy")
