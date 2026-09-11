"""DART 전자공시 수집기 (PRD F-05, 소스 등급 A). 구현은 2단계 G 항목.

2단계 구현 시 유의
- 임원현황 API 로 성명·생년월·직위·등기여부·상근여부·담당업무·주요경력·재직기간·임기만료일을 받는다.
- API 키는 환경변수(DART_API_KEY)에서만 읽는다.
- rate limit·재시도·에러 로깅을 넣는다.
- 동명이인은 생년월 + 소속 이력으로 판정하고, 신뢰도가 낮으면 ReviewQueue 로 보낸다.
"""

from __future__ import annotations

import os

from collectors.base import CollectedFact, is_live_mode
from core.constants import SOURCE_TIER_A


class DartCollector:
    name = "dart"
    source_tier = SOURCE_TIER_A

    def __init__(self) -> None:
        self.api_key = os.getenv("DART_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key) and is_live_mode()

    def collect(self, corp_code: str | None = None, **kwargs) -> list[CollectedFact]:
        if not is_live_mode():
            # 더미 모드에서는 외부 호출을 하지 않는다
            return []
        raise NotImplementedError("DART 수집은 2단계(G)에서 구현합니다.")
