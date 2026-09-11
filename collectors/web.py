"""기업 홈페이지·기관 프로필 수집기 (PRD F-05, 소스 등급 B).

⚠️ **범용 베이스워크만 제공한다.** 회사마다 홈페이지 구조가 전부 달라서, "경영진 소개"
페이지에서 이름·직위·약력을 정확히 분리해 뽑아내는 것은 사이트별 튜닝 없이는 신뢰도가
낮다 — 잘못 뽑으면 엉뚱한 문장을 사실인 것처럼 저장하는 위험이 있다(F-04-2 환각 방지
원칙과 같은 이유). 그래서 이 모듈은 의도적으로 다음까지만 한다:

  1) robots.txt 확인 후 페이지를 가져온다(이미 1단계부터 있던 가드, §5.2 로봇 배제 준수).
  2) <title>, <meta name="description">, 본문 <p> 텍스트를 일반적인 방식으로 뽑는다.
  3) CollectedFact 로 포장해 반환한다 — 이 스니펫이 실제로 원하는 내용(예: 경영진 소개)인지는
     사람이 검수(F-08)에서 반드시 확인해야 한다. 이 함수의 출력을 자동으로 신뢰해 저장하지 말 것.

특정 회사를 대상으로 한 정밀 추출(예: '경영진' 표에서 이름·직위 행 단위로 뽑기)이 필요하면
이 모듈의 `extract_generic()` 대신 회사별 파서를 새로 만들어야 한다.
"""

from __future__ import annotations

from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from collectors.base import CollectedFact, assert_source_allowed, is_live_mode
from core.constants import SOURCE_TIER_B

USER_AGENT = "IndependentDirectorPoolBot/1.0 (internal use)"
MAX_PARAGRAPHS = 15
MAX_SNIPPET_LEN = 500


class RobotsDisallowedError(PermissionError):
    """robots.txt 가 수집을 허용하지 않는 경로."""


class FetchError(RuntimeError):
    """페이지를 가져오지 못했거나(HTTP 오류) 추출할 텍스트가 없을 때."""


def can_fetch(url: str, user_agent: str = USER_AGENT) -> bool:
    assert_source_allowed(url)
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        # robots.txt 를 읽을 수 없으면 보수적으로 거부한다
        return False
    return parser.can_fetch(user_agent, url)


def fetch_page(url: str, user_agent: str = USER_AGENT, timeout: int = 15) -> str:
    """robots.txt 를 다시 한번 확인한 뒤(이중 방어) 페이지 원문 HTML을 가져온다."""
    if not can_fetch(url, user_agent):
        raise RobotsDisallowedError(f"robots.txt 가 수집을 허용하지 않습니다: {url}")
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding  # 한글 페이지 인코딩 오탐 보정
    return resp.text


def extract_generic(html_text: str, max_paragraphs: int = MAX_PARAGRAPHS) -> dict[str, str]:
    """제목·메타설명·본문 문단을 일반적인 방식으로 뽑는다. 사이트 구조를 가정하지 않는다."""
    soup = BeautifulSoup(html_text, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    description = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content"):
        description = meta["content"].strip()

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    body_text = " ".join(paragraphs[:max_paragraphs])

    return {"title": title, "description": description, "body_text": body_text}


def page_to_fact(url: str, extracted: dict[str, str]) -> CollectedFact:
    snippet = (extracted.get("description") or extracted.get("body_text") or extracted.get("title") or "").strip()
    if not snippet:
        raise FetchError(f"페이지에서 추출할 텍스트가 없습니다: {url}")
    return CollectedFact(
        publisher=urlparse(url).hostname or url,
        doc_title=extracted.get("title") or "기업 홈페이지",
        url=url,
        source_tier=SOURCE_TIER_B,
        quote_snippet=snippet[:MAX_SNIPPET_LEN],
        payload=extracted,
    )


class WebCollector:
    name = "web"
    source_tier = SOURCE_TIER_B

    def collect(self, url: str | None = None, **kwargs) -> list[CollectedFact]:
        if not is_live_mode():
            return []
        if not url:
            raise ValueError("url 은 필수입니다.")
        html_text = fetch_page(url)
        extracted = extract_generic(html_text)
        return [page_to_fact(url, extracted)]
