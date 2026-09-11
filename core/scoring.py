"""적합도 점수 (PRD F-06). 2단계 F 항목에서 구현한다.

1단계에서 점수를 만들어 두지 않는 이유
- 근거 없는 숫자를 화면에 띄우면 담당자가 그것을 판단 근거로 삼는다.
  구현 전까지는 '미산출'로 표시하고 정렬은 데이터 최신순으로 대체한다. (core/search.py)

2단계 구현 시 가중치는 아래 키로 AppSetting 에 추가하고 하드코딩하지 않는다.
"""

from __future__ import annotations

WEIGHT_KEYS = {
    "expertise_match": "score.weight.expertise_match",   # 40
    "skill_gap": "score.weight.skill_gap",               # 20
    "career_level": "score.weight.career_level",         # 15
    "availability": "score.weight.availability",         # 15
    "risk_penalty": "score.weight.risk_penalty",         # 10
}

DISCLAIMER = "적합도 점수는 보조 지표이며, 최종 판단은 담당자·법무 검토로 확정됩니다."

NOT_IMPLEMENTED_LABEL = "미산출"


def fit_score(person_id: int) -> float | None:  # pragma: no cover - 2단계 구현
    """아직 산출하지 않는다. 호출부는 None 을 '미산출'로 표시할 것."""
    return None
