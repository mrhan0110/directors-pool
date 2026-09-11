"""평판 정량 신호 (PRD F-03 (5)).

기사량 추이·논조 분포·주요 주제를 집계한다. 미확인 건은 따로 센다 — 화면에서
'언론 보도 존재, 사실관계 미확인'으로 구분 표기하고 자동 점수에는 반영하지 않는다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

POLARITIES = ("긍정", "중립", "부정")
FINAL_STATUSES = ("확정", "무혐의", "종결")


@dataclass
class ReputationSignals:
    by_year: dict[int, dict[str, int]] = field(default_factory=dict)
    topics: list[tuple[str, int]] = field(default_factory=list)
    verified: int = 0
    unverified: int = 0
    verified_negative: int = 0


def signals(reputations) -> ReputationSignals:
    out = ReputationSignals()
    topics: Counter = Counter()
    for r in reputations:
        if r.verified_yn:
            out.verified += 1
            if r.polarity == "부정":
                out.verified_negative += 1
        else:
            out.unverified += 1
        if r.category:
            topics[r.category] += 1
        if r.event_date is not None:
            year = out.by_year.setdefault(r.event_date.year, {p: 0 for p in POLARITIES})
            if r.polarity in year:
                year[r.polarity] += 1
    out.by_year = dict(sorted(out.by_year.items()))
    out.topics = topics.most_common(5)
    return out


def status_parts(r) -> dict[str, str]:
    """부정 이슈 표기 항목: 사실관계 / 시점 / 진행경과 / 최종 결과 (PRD §5.2)."""
    status = r.status or "미상"
    return {
        "사실관계": r.summary if r.verified_yn else f"{r.summary} — 언론 보도 존재, 사실관계 미확인",
        "시점": r.event_date.isoformat() if r.event_date else "미상",
        "진행경과": status,
        "최종 결과": status if status in FINAL_STATUSES else "미확정",
    }
