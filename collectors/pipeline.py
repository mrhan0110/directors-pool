"""실제 수집기(DART 등) → core.ingest 적재 파이프라인 연결.

수집기(collectors/*)는 원본 값 그대로의 CollectedFact/payload 를 반환하고, 이 모듈이
core.ingest 의 인물 식별·사실 적재 API 로 연결한다. 더미 모드는 이 모듈을 쓰지 않고
`core.ingest.run_dummy_collection()` 을 그대로 쓴다(§G, 더미도 실제와 같은 파이프라인을 탄다).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core import constants as C
from core import ingest, settings
from collectors.base import BlockedSourceError
from collectors.dart import (
    DartCollector,
    REPRT_CODE_ANNUAL,
    classify_role_level,
    is_full_time,
    is_registered,
    parse_birth_year,
    parse_dart_date,
    row_to_fact,
)
from collectors.news import NewsCollector, classify_polarity, item_to_fact
from data.models import Reputation, Source
from data.session import session_scope

_STAT_KEYS = (
    "rows", "created_person", "matched_person", "queued_identity", "blocked",
    "facts_created", "facts_updated", "conflicts_recorded", "queued_conflicts", "skipped",
)


def _empty_stats() -> dict[str, int]:
    return {k: 0 for k in _STAT_KEYS}


def _position_fields(row: dict, corp_name: str) -> dict:
    duties = (row.get("chrg_job") or row.get("main_career") or "").strip()
    period = (row.get("hffc_pd") or "").strip()
    if period:
        duties = f"{duties} (재직기간: {period})".strip()
    return {
        "org_name": corp_name,
        "title": (row.get("ofcps") or "").strip() or "미상",
        "role_level": classify_role_level(row.get("ofcps")),
        "is_registered_officer": is_registered(row.get("rgist_exctv_at")),
        "is_full_time": is_full_time(row.get("fte_at")),
        "term_end_date": parse_dart_date(row.get("tenure_end_on")),
        "duties": duties or None,
        "is_current": True,
    }


def ingest_dart_executives(corp_code: str, corp_name: str, bsns_year: str, reprt_code: str = REPRT_CODE_ANNUAL) -> dict[str, int]:
    """회사 1곳의 임원현황을 실제로 수집해 적재한다. 결과 통계를 반환한다."""
    collector = DartCollector()
    rows = collector.fetch_executives(corp_code, bsns_year, reprt_code)
    stats = _empty_stats()
    stats["rows"] = len(rows)

    for row in rows:
        name = (row.get("nm") or "").strip()
        if not name:
            stats["skipped"] += 1
            continue
        birth_year = parse_birth_year(row.get("birth_ym"))
        res = ingest.get_or_create_person(name, birth_year=birth_year, org_names=[corp_name])
        if res.status == "created":
            stats["created_person"] += 1
        elif res.status == "matched":
            stats["matched_person"] += 1
        elif res.status == "queued":
            stats["queued_identity"] += 1
            continue
        elif res.status == "blocked":
            stats["blocked"] += 1
            continue

        fact = row_to_fact(row, corp_name)
        outcome = ingest.ingest_fact("position", res.person_id, _position_fields(row, corp_name), fact)
        if outcome == ingest.OUT_CREATED:
            stats["facts_created"] += 1
        elif outcome == ingest.OUT_UPDATED:
            stats["facts_updated"] += 1
        elif outcome == ingest.OUT_CONFLICT_RECORDED:
            stats["conflicts_recorded"] += 1
        elif outcome == ingest.OUT_QUEUED_CONFLICT:
            stats["queued_conflicts"] += 1
    return stats


def parse_target_companies(raw_pairs: list[str]) -> list[tuple[str, str]]:
    """'corp_code:회사명' 문자열 목록 → (corp_code, 회사명) 튜플 목록. 형식이 아니면 건너뛴다."""
    out = []
    for pair in raw_pairs:
        if ":" not in pair:
            continue
        corp_code, corp_name = pair.split(":", 1)
        corp_code, corp_name = corp_code.strip(), corp_name.strip()
        if corp_code and corp_name:
            out.append((corp_code, corp_name))
    return out


def collect_configured_dart_targets(bsns_year: str, reprt_code: str = REPRT_CODE_ANNUAL) -> dict[str, int]:
    """AppSetting(collect.dart_target_companies)에 설정된 회사 전체를 수집한다."""
    targets = parse_target_companies(settings.get_list(C.SET_DART_TARGET_COMPANIES))
    if not targets:
        raise ValueError(
            "수집 대상이 설정되지 않았습니다. 관리자 화면 '운영 파라미터'에서 "
            "'collect.dart_target_companies'를 'corp_code:회사명' 형식(콤마로 여러 개)으로 입력하세요."
        )
    total = _empty_stats()
    for corp_code, corp_name in targets:
        result = ingest_dart_executives(corp_code, corp_name, bsns_year, reprt_code)
        for k, v in result.items():
            total[k] += v
    return total


# ------------------------------------------------------------------ 뉴스 → 평판(Reputation)

def _reputation_exists_for_url(s, person_id: int, url: str) -> bool:
    """이미 수집한 기사인지 확인한다(재수집 시 중복 적재 방지). 기사 1건 = 사실 1건이라
    core.ingest.ingest_fact 의 '자연키로 갱신' 방식이 아니라 URL 로 직접 중복을 막는다."""
    return s.execute(
        select(Reputation.reputation_id)
        .join(Source, Source.source_id == Reputation.source_id)
        .where(Reputation.person_id == person_id, Source.url == url)
    ).first() is not None


def ingest_news_for_person(person_id: int, person_name: str, context: str | None = None, display: int = 20) -> dict[str, int]:
    """특정 인물의 이름(+ 맥락어, 있으면 정확도 향상)으로 뉴스를 검색해 평판으로 적재한다.

    ⚠️ 동명이인 위험: 뉴스 검색은 이름 문자열만으로 걸러지므로, 흔한 이름이면 전혀 다른
    사람의 기사가 섞여 들어올 수 있다. 이 함수는 동명이인을 구분하지 않는다 — 전부
    verified_yn=False 로 적재되며, 검수(F-08) 화면에서 사람이 걸러내야 검수완료가 된다.
    가능하면 `context`(현재 소속 등)를 함께 넘겨 검색 정확도를 높인다.
    """
    collector = NewsCollector()
    query = f"{person_name} {context}".strip() if context else person_name
    items = collector.search(query, display=display, sort="date")

    stats = {"items": len(items), "created": 0, "skipped_duplicate": 0, "skipped_invalid": 0}
    for item in items:
        url = (item.get("originallink") or item.get("link") or "").strip()
        if not url:
            stats["skipped_invalid"] += 1
            continue
        try:
            fact = item_to_fact(item, query)
        except BlockedSourceError:
            stats["skipped_invalid"] += 1
            continue

        with session_scope() as s:
            if _reputation_exists_for_url(s, person_id, fact.url):
                stats["skipped_duplicate"] += 1
                continue
            published = date.fromisoformat(fact.published_date) if fact.published_date else None
            src = Source(
                publisher=fact.publisher, doc_title=fact.doc_title, published_date=published,
                url=fact.url, source_tier=fact.source_tier, quote_snippet=fact.quote_snippet,
            )
            s.add(src)
            s.flush()
            s.add(Reputation(
                person_id=person_id,
                polarity=classify_polarity(f"{fact.doc_title} {fact.quote_snippet}"),
                category="언론 보도",
                event_date=published,
                summary=fact.doc_title,
                status=None,
                verified_yn=False,
                source_id=src.source_id,
            ))
            stats["created"] += 1
    return stats
