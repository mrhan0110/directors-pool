"""기업 홈페이지·기관 프로필 수집기 (PRD F-05, 소스 등급 B). 구현은 2단계 G 항목.

1단계에서 미리 넣는 가드: robots.txt 확인 인터페이스.
크롤링 전 반드시 can_fetch() 를 통과해야 한다 (PRD §5.2 로봇 배제 준수).
"""

from __future__ import annotations

from urllib import robotparser
from urllib.parse import urljoin, urlparse

from collectors.base import CollectedFact, assert_source_allowed, is_live_mode
from core.constants import SOURCE_TIER_B

USER_AGENT = "IndependentDirectorPoolBot/1.0 (internal use)"


class RobotsDisallowedError(PermissionError):
    """robots.txt 가 수집을 허용하지 않는 경로."""


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


class WebCollector:
    name = "web"
    source_tier = SOURCE_TIER_B

    def collect(self, url: str | None = None, **kwargs) -> list[CollectedFact]:
        if not is_live_mode():
            return []
        if url and not can_fetch(url):
            raise RobotsDisallowedError(f"robots.txt 가 수집을 허용하지 않습니다: {url}")
        raise NotImplementedError("홈페이지 수집은 2단계(G)에서 구현합니다.")
