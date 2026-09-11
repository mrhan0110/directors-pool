"""실제 수집기(DART 등) → core.ingest 적재 파이프라인 연결.

수집기(collectors/*)는 원본 값 그대로의 CollectedFact/payload 를 반환하고, 이 모듈이
core.ingest 의 인물 식별·사실 적재 API 로 연결한다. 더미 모드는 이 모듈을 쓰지 않고
`core.ingest.run_dummy_collection()` 을 그대로 쓴다(§G, 더미도 실제와 같은 파이프라인을 탄다).
"""

from __future__ import annotations

from core import constants as C
from core import ingest, settings
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
