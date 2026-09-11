"""수집 적재 파이프라인 (PRD F-05, §8 정제 계층, §11).

더미 모드·실제 모드가 이 파이프라인을 함께 사용한다(§G 지시). 즉 더미데이터로 이 모듈을
테스트하면 실제 수집기가 붙었을 때의 동작도 함께 검증된다.

- 인물 식별: 이름 완전일치 후보 중 생년월·소속이력 겹침으로 점수를 매긴다.
  신뢰도(`identity.auto_merge_threshold`) 미만이면 자동 결합하지 않고 ReviewQueue
  `QUEUE_IDENTITY` 로 보낸다(§11, 동명이인 오식별 방지가 최우선이다).
- 사실 적재: 동일 항목(조직·직위 등 자연키)이 이미 있으면
  - `manually_edited=True` 인 행은 절대 자동으로 덮어쓰지 않고 ReviewQueue `QUEUE_CONFLICT`
    로 보낸다(F-08-4). payload 형식은 `core.review.resolve_alert` 가 그대로 처리할 수 있게 맞춘다.
  - 아니면 상위 신뢰등급(A>B>C) 값을 채택하고, 하위 값은 `FieldConflict` 로 병기한다(F-05-3).
- 보관기간 경과 자동 파기(§5.2) 및 삭제 요청 시 즉시 파기 + 재수집 차단(PersonBlocklist).
- URL 유효성 점검(F-05-5).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy import delete, select

from collectors.base import CollectedFact
from core import constants as C
from core import settings
from core.audit import log_change
from core.review import EDITABLE as REVIEW_EDITABLE
from data.models import (
    Achievement,
    ConsiderationCheck,
    Directorship,
    ExpertiseHistory,
    FieldConflict,
    Person,
    PersonBlocklist,
    PersonIndustry,
    PersonScore,
    PoolMember,
    Position,
    Reputation,
    ReviewLog,
    ReviewQueue,
    Source,
)
from data.session import session_scope

# ------------------------------------------------------------------ 원문 스냅샷 (F-05-6)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = PROJECT_ROOT / "storage" / "snapshots"


def save_snapshot(subdir: str, filename: str, content: bytes) -> str:
    """원문 스냅샷(HTML/PDF)을 내부 스토리지에 저장하고, Source.snapshot_path 에 넣을 상대경로를 반환한다."""
    target_dir = SNAPSHOT_ROOT / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_bytes(content)
    return str(path.relative_to(PROJECT_ROOT).as_posix())


# ------------------------------------------------------------------ 사실 적재

OUT_CREATED = "created"
OUT_UPDATED = "updated"
OUT_UNCHANGED = "unchanged"
OUT_CONFLICT_RECORDED = "conflict_recorded"
OUT_QUEUED_CONFLICT = "queued_conflict"
OUT_IGNORED_PROTECTED = "ignored_protected"

_MODELS: dict[str, type] = {
    "position": Position,
    "directorship": Directorship,
    "reputation": Reputation,
    "achievement": Achievement,
}
# 같은 사실인지 판별하는 자연키. 값이 바뀌어도 '동일 건의 갱신'으로 취급한다.
MATCH_KEYS: dict[str, tuple[str, ...]] = {
    "position": ("org_name", "title"),
    "directorship": ("company_name", "role_type"),
    "reputation": ("category", "event_date"),
    "achievement": ("category", "description"),
}
_PK: dict[str, str] = {
    "position": "position_id",
    "directorship": "directorship_id",
    "reputation": "reputation_id",
    "achievement": "achievement_id",
}


def _make_source(collected: CollectedFact) -> Source:
    published = date.fromisoformat(collected.published_date) if collected.published_date else None
    snapshot = (collected.payload or {}).get("snapshot_path") if collected.payload else None
    return Source(
        publisher=collected.publisher,
        doc_title=collected.doc_title,
        published_date=published,
        url=collected.url,
        source_tier=collected.source_tier,
        quote_snippet=collected.quote_snippet,
        snapshot_path=snapshot,
    )


def _disp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _prefer_new(existing: Source, new: Source) -> bool:
    """상위 신뢰등급을 우선하고, 등급이 같으면 발행일이 최근인 쪽을 우선한다 (F-05-3)."""
    existing_order = C.SOURCE_TIER_ORDER.get(existing.source_tier, 9)
    new_order = C.SOURCE_TIER_ORDER.get(new.source_tier, 9)
    if new_order != existing_order:
        return new_order < existing_order
    if new.published_date is None:
        return False
    if existing.published_date is None:
        return True
    return new.published_date > existing.published_date


def ingest_fact(entity: str, person_id: int, fields: dict[str, Any], collected: CollectedFact) -> str:
    """수집된 사실 1건을 적재한다. 반환값은 OUT_* 상수 중 하나."""
    model = _MODELS.get(entity)
    if model is None:
        raise ValueError(f"수집 파이프라인이 지원하지 않는 항목입니다: {entity}")
    keys = MATCH_KEYS[entity]
    editable = REVIEW_EDITABLE.get(entity, {})

    with session_scope() as s:
        filters = [getattr(model, k) == fields.get(k) for k in keys]
        row = s.execute(select(model).where(model.person_id == person_id, *filters)).scalars().first()

        if row is None:
            src = _make_source(collected)
            s.add(src)
            s.flush()
            kwargs = dict(fields)
            kwargs["person_id"] = person_id
            kwargs["source_id"] = src.source_id
            s.add(model(**kwargs))
            return OUT_CREATED

        diff = {k: v for k, v in fields.items() if hasattr(row, k) and getattr(row, k) != v}
        if not diff:
            return OUT_UNCHANGED

        entity_id = getattr(row, _PK[entity])

        if row.manually_edited:
            # 검수자가 고친 값은 자동 갱신이 덮어쓰지 않는다 (F-08-4). 편집 가능한 항목만 알림으로 올린다.
            queued = 0
            for field, new_value in diff.items():
                if field not in editable:
                    continue
                s.add(ReviewQueue(
                    queue_type=C.QUEUE_CONFLICT,
                    payload={
                        "person_id": person_id,
                        "entity": entity,
                        "entity_id": entity_id,
                        "field": field,
                        "current_value": _disp(getattr(row, field)),
                        "new_value": _disp(new_value),
                    },
                ))
                queued += 1
            return OUT_QUEUED_CONFLICT if queued else OUT_IGNORED_PROTECTED

        existing_source = s.get(Source, row.source_id)
        new_source = _make_source(collected)
        s.add(new_source)
        s.flush()
        adopt_new = _prefer_new(existing_source, new_source)

        for field, new_value in diff.items():
            if field not in editable:
                if adopt_new:
                    setattr(row, field, new_value)
                continue
            current = getattr(row, field)
            if adopt_new:
                s.add(FieldConflict(
                    person_id=person_id, entity=entity, entity_id=entity_id, field=field,
                    adopted_value=_disp(new_value), adopted_source_id=new_source.source_id,
                    alt_value=_disp(current), alt_source_id=existing_source.source_id,
                ))
                setattr(row, field, new_value)
            else:
                s.add(FieldConflict(
                    person_id=person_id, entity=entity, entity_id=entity_id, field=field,
                    adopted_value=_disp(current), adopted_source_id=existing_source.source_id,
                    alt_value=_disp(new_value), alt_source_id=new_source.source_id,
                ))

        if adopt_new:
            row.source_id = new_source.source_id
            return OUT_UPDATED
        return OUT_CONFLICT_RECORDED


def ingest_industry(person_id: int, industry_code: str, collected: CollectedFact) -> str:
    """산업 도메인 경험(PersonIndustry)은 존재 여부만 사실이므로 최초 1건만 적재한다."""
    with session_scope() as s:
        exists = s.execute(
            select(PersonIndustry.id).where(
                PersonIndustry.person_id == person_id, PersonIndustry.industry_code == industry_code
            )
        ).first()
        if exists:
            return OUT_UNCHANGED
        src = _make_source(collected)
        s.add(src)
        s.flush()
        s.add(PersonIndustry(person_id=person_id, industry_code=industry_code, source_id=src.source_id))
        return OUT_CREATED


# ------------------------------------------------------------------ 인물 식별 (동명이인, §11)


def identity_hash(name_ko: str, birth_year: int | None) -> str:
    """블록리스트에 원문 이름 대신 저장하는 해시 (개인정보 최소화, §5.2)."""
    raw = f"{name_ko.strip()}|{birth_year if birth_year is not None else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _org_names_of(s, person_id: int) -> set[str]:
    pos = set(s.execute(select(Position.org_name).where(Position.person_id == person_id)).scalars())
    dirs = set(s.execute(select(Directorship.company_name).where(Directorship.person_id == person_id)).scalars())
    return pos | dirs


def _identity_score(s, candidate: Person, birth_year: int | None, org_names: Sequence[str], gender: str | None) -> float:
    score = 0.0
    if birth_year is not None and candidate.birth_year is not None:
        score += 0.5 if birth_year == candidate.birth_year else -0.5
    if gender and candidate.gender and gender == candidate.gender:
        score += 0.1
    if org_names:
        overlap = set(org_names) & _org_names_of(s, candidate.person_id)
        if overlap:
            score += 0.5 * min(1.0, len(overlap) / len(set(org_names)))
    return max(0.0, min(1.0, score))


@dataclass(frozen=True)
class IdentityResolution:
    person_id: int | None
    status: str  # matched / new / created / queued / blocked
    score: float | None = None


def resolve_person(
    name_ko: str,
    birth_year: int | None = None,
    gender: str | None = None,
    org_names: Sequence[str] = (),
) -> IdentityResolution:
    """이름이 겹치는 기존 인물이 있는지 판별한다. 새 인물은 만들지 않는다."""
    with session_scope() as s:
        candidates = list(s.execute(select(Person).where(Person.name_ko == name_ko)).scalars())
        if not candidates:
            blocked = s.execute(
                select(PersonBlocklist.id).where(
                    PersonBlocklist.identity_hash == identity_hash(name_ko, birth_year)
                )
            ).first()
            return IdentityResolution(None, "blocked" if blocked else "new")

        scored = sorted(
            ((c, _identity_score(s, c, birth_year, org_names, gender)) for c in candidates),
            key=lambda t: -t[1],
        )
        best, best_score = scored[0]
        threshold = settings.get_float(C.SET_IDENTITY_MERGE_THRESHOLD)
        if best_score >= threshold:
            return IdentityResolution(best.person_id, "matched", best_score)

        s.add(ReviewQueue(
            queue_type=C.QUEUE_IDENTITY,
            payload={
                "name_ko": name_ko,
                "birth_year": birth_year,
                "gender": gender,
                "org_names": list(org_names),
                "candidates": [{"person_id": c.person_id, "score": sc} for c, sc in scored],
            },
        ))
    log_change(None, "ingest", "identity_queue", detail=name_ko)
    return IdentityResolution(None, "queued", best_score)


def get_or_create_person(
    name_ko: str,
    birth_year: int | None = None,
    gender: str | None = None,
    org_names: Sequence[str] = (),
    **extra: Any,
) -> IdentityResolution:
    """식별 결과가 '신규'일 때만 인물을 만든다. 애매하거나 차단된 경우 호출부는 적재를 건너뛴다."""
    res = resolve_person(name_ko, birth_year, gender, org_names)
    if res.status != "new":
        return res
    years = settings.get_int(C.SET_RETENTION_YEARS)
    with session_scope() as s:
        person = Person(
            name_ko=name_ko,
            birth_year=birth_year,
            gender=gender,
            age_estimated_yn=True,
            retention_until=date.today() + timedelta(days=365 * years),
            **extra,
        )
        s.add(person)
        s.flush()
        person_id = person.person_id
    log_change(None, "ingest", "person_create", str(person_id), name_ko)
    return IdentityResolution(person_id, "created")


# ------------------------------------------------------------------ 보관기간·파기 (§5.2)


def _purge_dependents(s, person_id: int) -> None:
    """Person 관계 중 cascade 가 걸리지 않은 부속 테이블을 함께 정리한다."""
    for model in (PersonIndustry, PersonScore, ConsiderationCheck, ReviewLog, ExpertiseHistory):
        s.execute(delete(model).where(model.person_id == person_id))
    s.execute(delete(PoolMember).where(PoolMember.person_id == person_id))


def purge_expired(today: date | None = None) -> int:
    """`retention_until` 경과 후보를 자동 파기한다 (PRD §5.2, 인수기준 #11)."""
    today = today or date.today()
    with session_scope() as s:
        rows = list(
            s.execute(
                select(Person).where(Person.retention_until.is_not(None), Person.retention_until < today)
            ).scalars()
        )
        for person in rows:
            _purge_dependents(s, person.person_id)
            s.delete(person)
        count = len(rows)
    log_change(None, "ingest", "purge_expired", detail=f"{count}건")
    return count


def delete_person_request(person_id: int, reason: str, user_id: int | None = None) -> None:
    """후보자 삭제 요청: 즉시 파기 + 재수집 차단 (PRD §5.2)."""
    if not reason or not reason.strip():
        raise ValueError("삭제 사유를 입력하세요.")
    with session_scope() as s:
        person = s.get(Person, person_id)
        if person is None:
            raise LookupError(f"후보를 찾을 수 없습니다: {person_id}")
        h = identity_hash(person.name_ko, person.birth_year)
        _purge_dependents(s, person_id)
        s.delete(person)
        if not s.execute(select(PersonBlocklist.id).where(PersonBlocklist.identity_hash == h)).first():
            s.add(PersonBlocklist(identity_hash=h, reason=reason.strip()))
    log_change(user_id, "ingest", "delete_request", str(person_id), reason.strip())


# ------------------------------------------------------------------ URL 점검 (F-05-5)


def _default_fetch(url: str) -> bool:
    import urllib.request

    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - 내부 점검용 고정 스킴
            return 200 <= resp.status < 400
    except Exception:
        return False


def check_urls(fetcher: Callable[[str], bool] | None = None, limit: int | None = None) -> dict[str, int]:
    """출처 URL 유효성을 점검하고 `url_alive_yn` 을 갱신한다 (F-05-5)."""
    fetcher = fetcher or _default_fetch
    dead = 0
    with session_scope() as s:
        stmt = select(Source)
        if limit:
            stmt = stmt.limit(limit)
        rows = list(s.execute(stmt).scalars())
        for src in rows:
            alive = fetcher(src.url)
            src.url_alive_yn = alive
            if not alive:
                dead += 1
        checked = len(rows)
    log_change(None, "ingest", "url_check", detail=f"checked={checked} dead={dead}")
    return {"checked": checked, "dead": dead}


# ------------------------------------------------------------------ 더미 수집 (실제와 같은 파이프라인 통과용)


def _dummy_source(tier: str, idx: int, days_ago: int = 0) -> CollectedFact:
    publisher = {C.SOURCE_TIER_A: "가상 DART", C.SOURCE_TIER_B: "가상 기업 홈페이지", C.SOURCE_TIER_C: "가상 뉴스"}[tier]
    title = {C.SOURCE_TIER_A: "임원현황 공시", C.SOURCE_TIER_B: "경영진 소개", C.SOURCE_TIER_C: "인사 기사"}[tier]
    host = {C.SOURCE_TIER_A: "dart.example.com/collect", C.SOURCE_TIER_B: "company.example.com/about",
            C.SOURCE_TIER_C: "news.example.com/article"}[tier]
    return CollectedFact(
        publisher=publisher,
        doc_title=title,
        url=f"https://{host}/{idx:06d}",
        source_tier=tier,
        quote_snippet=f"(더미 수집) 근거 인용 {idx}",
        published_date=(date.today() - timedelta(days=days_ago)).isoformat(),
    )


def run_dummy_collection(count: int = 5, rng_seed: int = 20260911) -> dict[str, int]:
    """실제 수집기 없이도 전체 적재 파이프라인(식별·충돌·큐잉)을 검증하는 더미 모드 수집.

    `batch.run collect` 의 기본 경로(DATA_MODE=dummy)로 실행된다.
    """
    rng = random.Random(rng_seed)
    stats = {
        "created_person": 0, "matched_person": 0, "queued_identity": 0, "blocked": 0,
        "facts_created": 0, "facts_updated": 0, "conflicts_recorded": 0,
        "queued_conflicts": 0, "industries": 0,
    }
    idx = 0
    companies = ["가상전자", "가상바이오", "가상금융지주"]

    for i in range(count):
        idx += 1
        name = f"수집더미{rng.randint(10000, 99999)} 홍{i:03d}"
        birth_year = rng.randint(1950, 1978)
        res = get_or_create_person(name, birth_year=birth_year, gender=rng.choice(["M", "F"]))
        if res.status != "created":
            continue
        stats["created_person"] += 1
        org = rng.choice(companies)

        outcome = ingest_fact(
            "position", res.person_id,
            {"org_name": org, "title": "상무", "role_level": "L2", "job_l1_code": "CORP",
             "job_l2_code": "CORP_EXE", "is_current": True, "is_full_time": True,
             "start_date": date.today() - timedelta(days=365 * 3), "duties": "경영전략 담당"},
            _dummy_source(C.SOURCE_TIER_A, idx),
        )
        if outcome == OUT_CREATED:
            stats["facts_created"] += 1

        idx += 1
        if ingest_industry(res.person_id, "IND_FIN", _dummy_source(C.SOURCE_TIER_B, idx)) == OUT_CREATED:
            stats["industries"] += 1

        # 후속 수집(하위 등급): 직위 문구가 다르지만 이미 상위 등급 값이 있으므로 대체 정보로만 병기
        idx += 1
        outcome2 = ingest_fact(
            "position", res.person_id,
            {"org_name": org, "title": "전무", "role_level": "L2", "job_l1_code": "CORP",
             "job_l2_code": "CORP_EXE", "is_current": True, "is_full_time": True,
             "start_date": date.today() - timedelta(days=365 * 3), "duties": "경영전략 담당"},
            _dummy_source(C.SOURCE_TIER_C, idx),
        )
        if outcome2 == OUT_CONFLICT_RECORDED:
            stats["conflicts_recorded"] += 1
        elif outcome2 == OUT_UPDATED:
            stats["facts_updated"] += 1

    # 동일인 재확인 수집 — 생년월 + 소속이력 겹침으로 자동 매칭
    idx += 1
    name0 = f"수집더미재확인{rng.randint(1000, 9999)}"
    birth0 = rng.randint(1950, 1978)
    first = get_or_create_person(name0, birth_year=birth0, gender="M")
    if first.status == "created":
        stats["created_person"] += 1
        ingest_fact(
            "position", first.person_id,
            {"org_name": "가상중공업", "title": "부사장", "role_level": "L1", "job_l1_code": "CORP",
             "job_l2_code": "CORP_EXE", "is_current": True, "is_full_time": True,
             "start_date": date.today() - timedelta(days=365 * 4), "duties": "생산 총괄"},
            _dummy_source(C.SOURCE_TIER_A, idx),
        )
        again = resolve_person(name0, birth_year=birth0, org_names=["가상중공업"])
        if again.status == "matched":
            stats["matched_person"] += 1

    # 동명이인 애매한 케이스 — 생년월 불일치로 자동 결합하지 않고 큐로
    idx += 1
    dup_name = f"수집더미동명{rng.randint(1000, 9999)}"
    if get_or_create_person(dup_name, birth_year=1960, gender="M").status == "created":
        stats["created_person"] += 1
    if resolve_person(dup_name, birth_year=1975, org_names=[]).status == "queued":
        stats["queued_identity"] += 1

    # 삭제 요청으로 블록리스트에 오른 인물의 재수집 시도 — 차단
    idx += 1
    blocked_name = f"수집더미삭제{rng.randint(1000, 9999)}"
    b = get_or_create_person(blocked_name, birth_year=1965, gender="F")
    if b.status == "created":
        delete_person_request(b.person_id, "본인 삭제 요청", user_id=None)
        if get_or_create_person(blocked_name, birth_year=1965, gender="F").status == "blocked":
            stats["blocked"] += 1

    log_change(None, "ingest", "dummy_collect", detail=str(stats))
    return stats
