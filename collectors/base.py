"""수집기 공통 인터페이스 (PRD F-05).

1단계는 인터페이스와 '차단 가드'만 구현한다. 실제 수집은 2단계 G 항목.

수집기는 Streamlit 프로세스가 아니라 별도 배치로 실행한다 (PRD F-09-8).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from core.constants import SOURCE_DOMAIN_BLOCKLIST


class BlockedSourceError(ValueError):
    """화이트리스트 정책상 수집이 금지된 출처 (PRD F-05 제외 목록, 불변규칙 7)."""


@dataclass
class CollectedFact:
    """수집 결과 1건. 출처 메타데이터가 없으면 만들 수 없다 (PRD F-05-1)."""

    publisher: str
    doc_title: str
    url: str
    source_tier: str
    quote_snippet: str
    published_date: str | None = None
    payload: dict | None = None

    def __post_init__(self) -> None:
        assert_source_allowed(self.url)
        if not self.quote_snippet or not self.quote_snippet.strip():
            raise ValueError("근거 인용 스니펫 없이 사실을 수집할 수 없습니다. PRD F-05-1")


def assert_source_allowed(url: str) -> None:
    """익명 커뮤니티·SNS·블로그·위키 차단. 수집 단계에서 원천 배제한다."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise BlockedSourceError(f"URL 을 해석할 수 없습니다: {url}")
    for blocked in SOURCE_DOMAIN_BLOCKLIST:
        if host == blocked or host.endswith("." + blocked):
            raise BlockedSourceError(
                f"정책상 수집이 금지된 출처입니다: {host} (PRD F-05 제외 목록)"
            )


def is_live_mode() -> bool:
    """DATA_MODE=live 일 때만 실제 외부 호출을 허용한다. 기본값은 dummy."""
    return os.getenv("DATA_MODE", "dummy").lower() == "live"


class Collector(Protocol):
    name: str
    source_tier: str

    def collect(self, **kwargs) -> list[CollectedFact]:
        ...
