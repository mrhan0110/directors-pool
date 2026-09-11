"""뉴스 수집기 (PRD F-05, 소스 등급 C). 구현은 2단계 G 항목.

원칙
- 최근 3년 이내 기사를 기본 범위로 한다(중대 이슈는 기간 제한 없음).
- 수집된 기사 단독 근거로 부정 평판을 '확정' 처리하지 않는다.
  verified_yn=False 로 두고 검수자가 확인한다. (PRD F-03 (5))
- API 키 미발급 시 비활성 상태로 동작한다.
"""

from __future__ import annotations

import os

from collectors.base import CollectedFact, is_live_mode
from core.constants import SOURCE_TIER_C


class NewsCollector:
    name = "news"
    source_tier = SOURCE_TIER_C

    def __init__(self) -> None:
        self.api_key = os.getenv("NEWS_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key) and is_live_mode()

    def collect(self, person_name: str | None = None, **kwargs) -> list[CollectedFact]:
        if not self.available():
            return []
        raise NotImplementedError("뉴스 수집은 2단계(G)에서 구현합니다.")
