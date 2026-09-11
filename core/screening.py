"""결격·리스크 스크리닝 룰 엔진 (PRD §5.1, R-01~R-08).

1단계에서는 인터페이스와 집계 로직만 둔다. 개별 룰 판정은 2단계 E 항목이다.

설계 고정 사항 (2단계에서 지킬 것)
- 임계값은 전부 AppSetting 에서 읽는다. 이 모듈에 숫자를 쓰지 않는다. (불변규칙 4)
- 판정 결과에는 반드시 사유(reason)와 근거 데이터를 남긴다.
- 사람의 자격을 부정하는 판정이므로, 근거가 불충분하면 fail 이 아니라 warn 으로 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from core import constants as C
from data.models import ScreeningResult
from data.session import session_scope


@dataclass(frozen=True)
class RuleVerdict:
    rule_id: str
    result: str  # pass / warn / fail
    reason: str | None = None


def worst(results: list[str]) -> str:
    """여러 룰 판정 중 가장 나쁜 것을 후보의 대표 상태로 본다."""
    if not results:
        return C.SCREEN_PASS
    return max(results, key=lambda r: C.SCREEN_ORDER.get(r, 0))


def status_of(person_id: int) -> str:
    with session_scope() as s:
        rows = s.execute(
            select(ScreeningResult.result).where(ScreeningResult.person_id == person_id)
        ).scalars()
        return worst(list(rows))


def verdicts_of(person_id: int) -> list[ScreeningResult]:
    with session_scope() as s:
        return list(
            s.execute(
                select(ScreeningResult)
                .where(ScreeningResult.person_id == person_id)
                .order_by(ScreeningResult.rule_id)
            ).scalars()
        )


def evaluate(person_id: int) -> list[RuleVerdict]:  # pragma: no cover - 2단계 구현
    raise NotImplementedError(
        "룰 판정은 2단계(E)에서 구현합니다. "
        "구현 시 임계값은 core.settings 에서 읽고, 근거 없는 fail 판정을 만들지 마세요."
    )
