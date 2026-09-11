"""시드 + 분석 배치 결과 정합성 (PRD F-09-8, 인수 기준 #5).

conftest 의 seeded_db 가 seed.run(reset=True) 를 호출하며, seed 는 마지막에 analyze 배치를 돌린다.
"""

from __future__ import annotations

from sqlalchemy import func, select

from batch import run as batch
from core import constants as C
from core import screening
from data.models import AuditLog, Expertise, Person, PersonScore, ScreeningResult
from data.repository import source_integrity_report
from data.session import session_scope


def _count(model, *where) -> int:
    with session_scope() as s:
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return int(s.execute(stmt).scalar_one())


def test_every_person_is_screened_on_all_rules():
    persons = _count(Person)
    assert _count(ScreeningResult) >= persons * len(screening.RULES)


def test_every_person_has_score():
    assert _count(PersonScore) == _count(Person)


def test_classification_produced_grounded_expertise():
    assert _count(Expertise) > 0
    assert _count(Expertise, func.trim(Expertise.evidence_snippet) == "") == 0


def test_special_cases_trigger_disqualification_rules():
    """시드의 자사 재직(i=23)·장기재직(i=17) 케이스가 실제 룰로 결격 가능 판정된다."""
    assert _count(ScreeningResult, ScreeningResult.rule_id == "R-01",
                  ScreeningResult.result == C.SCREEN_FAIL) >= 1
    assert _count(ScreeningResult, ScreeningResult.rule_id == "R-05",
                  ScreeningResult.result == C.SCREEN_FAIL) >= 1


def test_no_fact_without_source():
    assert all(v == 0 for v in source_integrity_report().values())


def test_batch_cli_logs_start_and_finish():
    before = _count(AuditLog, AuditLog.entity == "batch")
    assert batch.main(["score"]) == 0
    with session_scope() as s:
        actions = list(s.execute(
            select(AuditLog.action).where(AuditLog.entity == "batch").order_by(AuditLog.id.desc()).limit(2)
        ).scalars())
    assert _count(AuditLog, AuditLog.entity == "batch") == before + 2
    assert actions == ["finish", "start"]
