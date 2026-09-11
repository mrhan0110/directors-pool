"""뉴스 수집기 (PRD F-05, 소스 등급 C).

**네이버 검색 오픈API '뉴스'**를 쓴다. PRD §14-2(뉴스 데이터 소스 계약: 빅카인즈/상용 API/
언론사 제휴)가 아직 결정되지 않았는데, 이 API는 무료·즉시 발급이라 결정이 나기 전까지 바로
쓸 수 있는 현실적인 대안으로 채택했다. 계약이 정해지면 이 모듈을 교체한다.

API 명세는 공식 자료로 확인했다(naver/naver-openapi-guide GitHub 저장소의 swagger 명세,
개발자 커뮤니티의 실응답 예시로 필드명 교차 확인):
  GET https://openapi.naver.com/v1/search/news.json
  헤더: X-Naver-Client-Id, X-Naver-Client-Secret
  파라미터: query(필수), display(10~100, 기본10), start(1~1000, 기본1), sort(sim|date)
  응답: {lastBuildDate, total, start, display,
         items: [{title, originallink, link, description, pubDate}]}
  title/description 에는 검색어 강조용 <b> 태그가 섞여 나온다 — 제거해야 한다.

원칙 (PRD F-03 (5), §5.2 명예훼손 리스크 관리)
- 뉴스 기사 단독 근거로는 확정 사실을 만들지 않는다 — 전부 `verified_yn=False` 로 적재하고
  사람이 검수(F-08)에서 확인해야 한다.
- 논조(긍정/중립/부정) 자동 분류는 키워드 기반의 아주 보수적인 추정치일 뿐이다.
  '부정' 신호 키워드가 뚜렷할 때만 부정으로 표시하고, 그 외엔 전부 중립으로 둔다
  (오분류로 인한 명예훼손 리스크를 낮추는 쪽으로 편향시킨다). 이 값은 자동 점수·스크리닝에
  들어가지 않는다(core/scoring.py 는 verified_yn=False 인 평판을 쓰지 않는다).
"""

from __future__ import annotations

import html
import os
import re
from datetime import date
from email.utils import parsedate_to_datetime

import requests

from collectors.base import BlockedSourceError, CollectedFact, is_live_mode
from core.constants import SOURCE_TIER_C

API_URL = "https://openapi.naver.com/v1/search/news.json"
DEFAULT_DISPLAY = 20
MAX_DISPLAY = 100

_TAG_RE = re.compile(r"</?b>")

# 아주 보수적인 부정 신호 키워드만 둔다(법적 분쟁·규제 제재·중대 이슈에 한정, R-06 판정 언어와 결을 맞춤).
# 이 목록에 없으면 전부 '중립'으로 분류한다 — 미상을 부정으로 잘못 찍는 것이 가장 위험하다.
_NEGATIVE_KEYWORDS = (
    "기소", "구속", "고발", "혐의", "제재", "징계", "소송", "패소", "횡령", "배임",
    "의혹", "수사", "압수수색", "탈세", "부실", "해임", "사퇴",
)


class NaverNewsApiError(RuntimeError):
    """네이버 뉴스검색 API 가 200 이 아닌 응답을 반환했을 때."""


def strip_tags(text: str | None) -> str:
    """응답의 <b> 강조 태그와 HTML 엔티티를 제거한다."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def parse_pub_date(value: str | None) -> date | None:
    """pubDate 는 RFC 822 형식(예: 'Mon, 22 Sep 2026 09:00:00 +0900')으로 온다."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.date() if dt else None
    except (TypeError, ValueError, IndexError):
        return None


def classify_polarity(text: str) -> str:
    """키워드 기반 1차 추정. verified_yn=False 로만 저장되며 자동 판정에 쓰이지 않는다."""
    return "부정" if any(k in (text or "") for k in _NEGATIVE_KEYWORDS) else "중립"


def item_to_fact(item: dict, query: str) -> CollectedFact:
    """네이버 뉴스검색 응답 1건 → CollectedFact. url 이 없으면 호출부에서 걸러야 한다."""
    title = strip_tags(item.get("title"))
    description = strip_tags(item.get("description"))
    url = (item.get("originallink") or item.get("link") or "").strip()
    publisher = _publisher_of(url)
    snippet = description or title or f"'{query}' 검색 결과"
    pub = parse_pub_date(item.get("pubDate"))
    return CollectedFact(
        publisher=publisher,
        doc_title=title or f"'{query}' 관련 기사",
        url=url,
        source_tier=SOURCE_TIER_C,
        quote_snippet=snippet[:500],
        published_date=pub.isoformat() if pub else None,
        payload=dict(item),
    )


def _publisher_of(url: str) -> str:
    """언론사명을 정확히 알 수 없으니(응답에 없음) 도메인을 그대로 쓴다 — 틀린 언론사명을
    추측해 붙이는 것보다 정직하다."""
    from urllib.parse import urlparse

    host = urlparse(url).hostname or url or "출처 미상"
    return host


class NewsCollector:
    name = "news"
    source_tier = SOURCE_TIER_C

    def __init__(self) -> None:
        self.client_id = os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    def available(self) -> bool:
        return bool(self.client_id and self.client_secret) and is_live_mode()

    def search(self, query: str, display: int = DEFAULT_DISPLAY, start: int = 1, sort: str = "date") -> list[dict]:
        """원본 응답의 items 리스트. 실패 시 NaverNewsApiError."""
        display = max(1, min(MAX_DISPLAY, display))
        resp = requests.get(
            API_URL,
            headers={"X-Naver-Client-Id": self.client_id, "X-Naver-Client-Secret": self.client_secret},
            params={"query": query, "display": display, "start": start, "sort": sort},
            timeout=15,
        )
        if resp.status_code != 200:
            raise NaverNewsApiError(f"네이버 뉴스검색 API 오류 {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("items") or []

    def collect(
        self, person_name: str | None = None, context: str | None = None,
        display: int = DEFAULT_DISPLAY, sort: str = "date", **kwargs,
    ) -> list[CollectedFact]:
        if not is_live_mode():
            return []
        if not self.available():
            raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 설정되지 않았습니다.")
        if not person_name:
            raise ValueError("person_name 은 필수입니다.")
        query = f"{person_name} {context}".strip() if context else person_name
        items = self.search(query, display=display, sort=sort)
        facts = []
        for item in items:
            url = (item.get("originallink") or item.get("link") or "").strip()
            if not url:
                continue
            try:
                facts.append(item_to_fact(item, query))
            except BlockedSourceError:
                continue  # 화이트리스트 밖 출처는 조용히 건너뛴다(F-05 제외 목록, 불변규칙 7)
        return facts
