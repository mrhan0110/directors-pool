"""수집 적재 파이프라인 테스트 (PRD F-05, §11, §5.2)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import select

from batch import run as batch
from collectors.base import BlockedSourceError, CollectedFact
from core import constants as C
from core import ingest
from core import review
from data.models import (
    AuditLog,
    FieldConflict,
    Person,
    PersonBlocklist,
    PersonIndustry,
    Position,
    ReviewQueue,
    Source,
)
from data.repository import source_integrity_report
from data.session import session_scope

RNG = random.Random(1)


def _uniq(prefix: str) -> str:
    return f"{prefix}{RNG.randint(1_000_000, 9_999_999)}"


def _cf(tier: str, tag: str, days_ago: int = 0) -> CollectedFact:
    return CollectedFact(
        publisher="테스트 발행처",
        doc_title="테스트 문서",
        url=f"https://dart.example.com/test/{tag}",
        source_tier=tier,
        quote_snippet=f"근거 인용 {tag}",
        published_date=(date.today() - timedelta(days=days_ago)).isoformat(),
    )


def _position_fields(org: str, title: str) -> dict:
    return {
        "org_name": org, "title": title, "role_level": "L2", "job_l1_code": "CORP",
        "job_l2_code": "CORP_EXE", "is_current": True, "is_full_time": True,
        "start_date": date.today() - timedelta(days=365 * 3), "duties": "테스트 담당업무",
    }


# ------------------------------------------------------------------ 원문 스냅샷 (F-05-6)

def test_save_snapshot_writes_file_and_returns_relative_path():
    name = f"snap_{RNG.randint(1000, 9999)}.html"
    rel_path = ingest.save_snapshot("test", name, "<html>테스트</html>".encode("utf-8"))
    full_path = ingest.PROJECT_ROOT / rel_path
    try:
        assert full_path.exists()
        assert full_path.read_text(encoding="utf-8") == "<html>테스트</html>"
        assert rel_path.replace("\\", "/") == f"storage/snapshots/test/{name}"
    finally:
        full_path.unlink(missing_ok=True)


# ------------------------------------------------------------------ 출처 가드 (재확인)

def test_collected_fact_rejects_blocked_domain():
    import pytest

    with pytest.raises(BlockedSourceError):
        CollectedFact(
            publisher="p", doc_title="d", url="https://blog.naver.com/x",
            source_tier=C.SOURCE_TIER_C, quote_snippet="x",
        )


# ------------------------------------------------------------------ 인물 식별

def test_get_or_create_person_then_resolves_as_matched():
    name = _uniq("식별테스트")
    res = ingest.get_or_create_person(name, birth_year=1970, gender="M")
    assert res.status == "created"
    ingest.ingest_fact("position", res.person_id, _position_fields("식별용회사", "상무"), _cf(C.SOURCE_TIER_A, "id1"))

    again = ingest.resolve_person(name, birth_year=1970, org_names=["식별용회사"])
    assert again.status == "matched"
    assert again.person_id == res.person_id


def test_ambiguous_identity_is_queued_not_auto_merged():
    name = _uniq("동명이인")
    first = ingest.get_or_create_person(name, birth_year=1960, gender="M")
    assert first.status == "created"

    before = len(list(_all(Person)))
    ambiguous = ingest.resolve_person(name, birth_year=1975, org_names=[])
    assert ambiguous.status == "queued"
    assert ambiguous.person_id is None
    assert len(list(_all(Person))) == before  # 자동으로 새 인물을 만들지 않는다

    with session_scope() as s:
        rows = list(s.execute(
            select(ReviewQueue).where(ReviewQueue.queue_type == C.QUEUE_IDENTITY)
        ).scalars())
    assert any((r.payload or {}).get("name_ko") == name for r in rows)


def _all(model):
    with session_scope() as s:
        return list(s.execute(select(model)).scalars())


# ------------------------------------------------------------------ 사실 적재 · 출처 충돌

def test_ingest_fact_creates_new_row_with_source():
    name = _uniq("신규사실")
    res = ingest.get_or_create_person(name, birth_year=1971)
    outcome = ingest.ingest_fact("position", res.person_id, _position_fields("가상전자", "상무"), _cf(C.SOURCE_TIER_A, "new1"))
    assert outcome == ingest.OUT_CREATED
    with session_scope() as s:
        row = s.execute(select(Position).where(Position.person_id == res.person_id)).scalar_one()
        assert row.source_id is not None
        assert s.get(Source, row.source_id) is not None


def test_ingest_fact_adopts_higher_tier_and_records_conflict():
    name = _uniq("등급채택")
    res = ingest.get_or_create_person(name, birth_year=1972)
    ingest.ingest_fact("position", res.person_id, _position_fields("가상전자", "상무"), _cf(C.SOURCE_TIER_B, "tierB"))

    outcome = ingest.ingest_fact(
        "position", res.person_id,
        {**_position_fields("가상전자", "상무"), "duties": "새 담당업무(A등급)"},
        _cf(C.SOURCE_TIER_A, "tierA"),
    )
    assert outcome == ingest.OUT_UPDATED
    with session_scope() as s:
        row = s.execute(select(Position).where(Position.person_id == res.person_id)).scalar_one()
        assert row.duties == "새 담당업무(A등급)"
        conflicts = list(s.execute(
            select(FieldConflict).where(FieldConflict.person_id == res.person_id, FieldConflict.field == "duties")
        ).scalars())
        assert conflicts and conflicts[0].adopted_value == "새 담당업무(A등급)"


def test_ingest_fact_keeps_higher_tier_and_records_alternative():
    name = _uniq("등급유지")
    res = ingest.get_or_create_person(name, birth_year=1973)
    ingest.ingest_fact("position", res.person_id, _position_fields("가상전자", "상무"), _cf(C.SOURCE_TIER_A, "keepA"))

    outcome = ingest.ingest_fact(
        "position", res.person_id,
        {**_position_fields("가상전자", "상무"), "duties": "낮은등급 주장(C등급)"},
        _cf(C.SOURCE_TIER_C, "keepC"),
    )
    assert outcome == ingest.OUT_CONFLICT_RECORDED
    with session_scope() as s:
        row = s.execute(select(Position).where(Position.person_id == res.person_id)).scalar_one()
        assert row.duties == "테스트 담당업무"  # 상위 등급 값 유지
        conflicts = list(s.execute(
            select(FieldConflict).where(FieldConflict.person_id == res.person_id, FieldConflict.field == "duties")
        ).scalars())
        assert conflicts and conflicts[0].alt_value == "낮은등급 주장(C등급)"


def test_ingest_fact_never_overwrites_manually_edited_row():
    name = _uniq("검수보호")
    res = ingest.get_or_create_person(name, birth_year=1974)
    ingest.ingest_fact("position", res.person_id, _position_fields("가상전자", "상무"), _cf(C.SOURCE_TIER_B, "man1"))
    with session_scope() as s:
        pos = s.execute(select(Position).where(Position.person_id == res.person_id)).scalar_one()
        pos_id = pos.position_id

    review.edit(res.person_id, "position", pos_id, "duties", "검수자가 직접 확인한 담당업무", user_id=None)

    outcome = ingest.ingest_fact(
        "position", res.person_id,
        {**_position_fields("가상전자", "상무"), "duties": "자동 수집이 덮어쓰려는 값"},
        _cf(C.SOURCE_TIER_A, "man2"),
    )
    assert outcome == ingest.OUT_QUEUED_CONFLICT
    with session_scope() as s:
        row = s.get(Position, pos_id)
        assert row.duties == "검수자가 직접 확인한 담당업무"  # 자동 갱신이 덮어쓰지 않았다

    alerts = review.open_alerts(res.person_id)
    assert len(alerts) == 1
    review.resolve_alert(alerts[0].id, user_id=None, accept_new=True)
    with session_scope() as s:
        row = s.get(Position, pos_id)
        assert row.duties == "자동 수집이 덮어쓰려는 값"  # 검수자가 승인하면 반영된다


def test_ingest_industry_is_idempotent():
    name = _uniq("산업멱등")
    res = ingest.get_or_create_person(name, birth_year=1975)
    first = ingest.ingest_industry(res.person_id, "IND_FIN", _cf(C.SOURCE_TIER_B, "ind1"))
    second = ingest.ingest_industry(res.person_id, "IND_FIN", _cf(C.SOURCE_TIER_B, "ind2"))
    assert first == ingest.OUT_CREATED
    assert second == ingest.OUT_UNCHANGED
    with session_scope() as s:
        count = len(list(s.execute(
            select(PersonIndustry).where(PersonIndustry.person_id == res.person_id)
        ).scalars()))
    assert count == 1


# ------------------------------------------------------------------ 보관·파기 (§5.2)

def test_purge_expired_deletes_only_expired_people():
    keep_name = _uniq("보관유지")
    gone_name = _uniq("보관만료")
    with session_scope() as s:
        s.add(Person(name_ko=keep_name, birth_year=1970, age_estimated_yn=True,
                      retention_until=date.today() + timedelta(days=30)))
        s.add(Person(name_ko=gone_name, birth_year=1970, age_estimated_yn=True,
                      retention_until=date.today() - timedelta(days=1)))

    purged = ingest.purge_expired()
    assert purged >= 1
    with session_scope() as s:
        assert s.execute(select(Person.person_id).where(Person.name_ko == keep_name)).first() is not None
        assert s.execute(select(Person.person_id).where(Person.name_ko == gone_name)).first() is None


def test_delete_person_request_blocks_recollection():
    name = _uniq("삭제요청")
    res = ingest.get_or_create_person(name, birth_year=1966, gender="F")
    ingest.delete_person_request(res.person_id, "본인 요청", user_id=None)

    with session_scope() as s:
        assert s.get(Person, res.person_id) is None
        assert s.execute(select(PersonBlocklist.id).where(
            PersonBlocklist.identity_hash == ingest.identity_hash(name, 1966)
        )).first() is not None

    retry = ingest.get_or_create_person(name, birth_year=1966, gender="F")
    assert retry.status == "blocked"
    assert retry.person_id is None


# ------------------------------------------------------------------ URL 점검 (F-05-5)

def test_check_urls_updates_alive_flag_with_injected_fetcher():
    name = _uniq("URL점검")
    res = ingest.get_or_create_person(name, birth_year=1968)
    ingest.ingest_fact("position", res.person_id, _position_fields("가상전자", "상무"), _cf(C.SOURCE_TIER_A, "urlchk"))
    with session_scope() as s:
        src_id = s.execute(
            select(Position.source_id).where(Position.person_id == res.person_id)
        ).scalar_one()

    result = ingest.check_urls(fetcher=lambda url: False, limit=None)
    assert result["checked"] >= 1
    assert result["dead"] >= 1
    with session_scope() as s:
        assert s.get(Source, src_id).url_alive_yn is False

    ingest.check_urls(fetcher=lambda url: True)
    with session_scope() as s:
        assert s.get(Source, src_id).url_alive_yn is True


# ------------------------------------------------------------------ 더미 수집 통합

def test_run_dummy_collection_end_to_end_keeps_source_integrity():
    stats = ingest.run_dummy_collection(count=3, rng_seed=777)
    assert stats["created_person"] >= 3
    assert stats["queued_identity"] == 1
    assert stats["blocked"] == 1
    assert all(v == 0 for v in source_integrity_report().values())


def _batch_log_count() -> int:
    with session_scope() as s:
        return len(list(s.execute(select(AuditLog).where(AuditLog.entity == "batch")).scalars()))


def test_batch_cli_collect_url_check_purge_log_start_finish(monkeypatch):
    # url-check 는 기본적으로 실제 네트워크 호출을 한다. 테스트에서는 빠르고 결정적이도록 가짜 fetcher 로 바꾼다.
    monkeypatch.setattr(ingest, "_default_fetch", lambda url: True)
    for job in ("collect", "url-check", "purge"):
        before = _batch_log_count()
        assert batch.main([job]) == 0
        with session_scope() as s:
            latest_actions = list(s.execute(
                select(AuditLog.action).where(AuditLog.entity == "batch").order_by(AuditLog.id.desc()).limit(2)
            ).scalars())
        assert _batch_log_count() == before + 2
        assert latest_actions == ["finish", "start"]
