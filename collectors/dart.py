"""DART 전자공시 수집기 (PRD F-05, 소스 등급 A).

API 명세는 DART 개발가이드('임원 현황', apiId 2019010)에서 확인했다.
  GET https://opendart.fss.or.kr/api/exctvSttus.json
  파라미터: crtfc_key(인증키), corp_code(8자리 고유번호), bsns_year(4자리), reprt_code(5자리)
  응답 필드: status/message/rcept_no/corp_cls/nm(성명)/birth_ym(생년월)/ofcps(직위)/
            rgist_exctv_at(등기임원여부)/fte_at(상근여부)/chrg_job(담당업무)/
            main_career(주요경력)/hffc_pd(재직기간)/tenure_end_on(임기만료일)

⚠️ 이 파일은 API 키가 없는 상태(개발 세션)에서 문서 스펙만으로 작성했다 — 실제 응답으로
아직 검증하지 못했다. 날짜·구분 필드가 문서와 다른 형식으로 올 가능성에 대비해 모든 파서가
방어적으로 동작하며(예외 대신 None), 첫 실제 호출 시 payload 원본을 함께 보관해 두어
(CollectedFact.payload) 문제가 있으면 사후 확인할 수 있게 했다.

corp_code(고유번호)는 별도의 '고유번호' API(corpCode.zip)로 회사명↔코드를 매핑해야 한다.
이 모듈은 그 매핑까지는 하지 않는다 — 관리자가 collect.dart_target_companies 설정값에
"corp_code:회사명" 쌍으로 직접 입력한다(core/settings.py).
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime

import requests

from collectors.base import CollectedFact, is_live_mode
from core.constants import SOURCE_TIER_A

API_BASE = "https://opendart.fss.or.kr/api"
REPRT_CODE_ANNUAL = "11011"    # 사업보고서
REPRT_CODE_HALF = "11012"      # 반기보고서
REPRT_CODE_Q1 = "11013"        # 1분기보고서
REPRT_CODE_Q3 = "11014"        # 3분기보고서


class DartApiError(RuntimeError):
    """DART 가 status != '000' 을 반환했을 때(잘못된 키·코드, 자료 없음 등)."""


def parse_birth_year(birth_ym: str | None) -> int | None:
    """'1970년 03월' 형식에서 연도만 뽑는다. 문서와 형식이 달라도 4자리 연도를 찾아본다."""
    if not birth_ym:
        return None
    m = re.search(r"(19|20)\d{2}", birth_ym)
    return int(m.group(0)) if m else None


def parse_dart_date(value: str | None) -> date | None:
    """DART 날짜 필드는 'YYYY-MM-DD' 또는 'YYYYMMDD' 로 오는 경우가 흔하다. 둘 다 시도한다."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# 직위 문구 → ROLE_LEVEL(L1~L4) 추정. 확신 없으면 분류하지 않는다(None) —
# 잘못된 등급 표기가 적합도 점수·검색 결과를 왜곡하는 것이 미분류보다 더 나쁘다.
_L1_KEYWORDS = ("대표이사", "회장", "총재", "원장", "청장")
_L2_KEYWORDS = ("부사장", "전무")
_L3_KEYWORDS = ("상무", "이사", "감사")
_L4_KEYWORDS = ("수석", "선임", "파트너", "연구위원")


def classify_role_level(title: str | None) -> str | None:
    """사외이사·감사위원처럼 이사회 내 '역할' 명칭은 조직 서열과 무관하므로 분류하지 않는다."""
    if not title:
        return None
    t = title.strip()
    if "사외이사" in t or "감사위원" in t:
        return None
    for level, keywords in (("L1", _L1_KEYWORDS), ("L2", _L2_KEYWORDS),
                             ("L3", _L3_KEYWORDS), ("L4", _L4_KEYWORDS)):
        if any(k in t for k in keywords):
            return level
    return None


def is_registered(rgist_exctv_at: str | None) -> bool:
    text = (rgist_exctv_at or "").strip()
    return "등기" in text and "미등기" not in text


def is_full_time(fte_at: str | None) -> bool:
    return (fte_at or "").strip() == "상근"


def document_url(rcept_no: str | None) -> str:
    if not rcept_no:
        return "https://dart.fss.or.kr/"
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def row_to_fact(row: dict, corp_name: str) -> CollectedFact:
    """DART 임원현황 원본 1행 → CollectedFact. 인물 매핑은 collectors/pipeline.py 가 담당한다."""
    name = (row.get("nm") or "").strip()
    title = (row.get("ofcps") or "").strip()
    snippet = f"{name} {title}".strip() or "DART 임원현황"
    if row.get("chrg_job"):
        snippet += f" — {row['chrg_job']}"
    return CollectedFact(
        publisher="금융감독원 전자공시시스템(DART)",
        doc_title=f"{corp_name} 임원 현황 (접수번호 {row.get('rcept_no', '미상')})",
        url=document_url(row.get("rcept_no")),
        source_tier=SOURCE_TIER_A,
        quote_snippet=snippet[:500],
        published_date=None,  # 이 API 응답에는 접수일자가 없다. 필요 시 공시검색 API 로 보강한다
        payload=dict(row),
    )


class DartCollector:
    name = "dart"
    source_tier = SOURCE_TIER_A

    def __init__(self) -> None:
        self.api_key = os.getenv("DART_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key) and is_live_mode()

    def fetch_executives(self, corp_code: str, bsns_year: str, reprt_code: str = REPRT_CODE_ANNUAL) -> list[dict]:
        """임원 현황 원본 응답. 실패 시 DartApiError, 네트워크 오류는 requests 예외 그대로 전파."""
        resp = requests.get(
            f"{API_BASE}/exctvSttus.json",
            params={
                "crtfc_key": self.api_key,
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status != "000":
            raise DartApiError(f"DART API 오류 {status}: {data.get('message')}")
        return data.get("list") or []

    def collect(
        self,
        corp_code: str | None = None,
        corp_name: str | None = None,
        bsns_year: str | None = None,
        reprt_code: str = REPRT_CODE_ANNUAL,
        **kwargs,
    ) -> list[CollectedFact]:
        if not is_live_mode():
            # 더미 모드에서는 외부 호출을 하지 않는다
            return []
        if not self.available():
            raise RuntimeError("DART_API_KEY 가 설정되지 않았습니다. .env 에 DART_API_KEY 를 넣으세요.")
        if not corp_code or not bsns_year:
            raise ValueError("corp_code, bsns_year 는 필수입니다.")
        rows = self.fetch_executives(corp_code, bsns_year, reprt_code)
        return [row_to_fact(row, corp_name or corp_code) for row in rows]
