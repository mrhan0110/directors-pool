"""경력 표출 규칙 (PRD F-03 (3)).

"최근 10개년, 임원급 이상 주요 보직만" 을 판정한다.
가장 틀리기 쉬운 로직이라 1단계에서 먼저 구현하고 테스트를 붙였다.

기준
- 기간: 재직 기간이 조회 기준일로부터 lookback 년 이내에 걸쳐 있으면 포함.
  (종료일이 기준 안에 들어오면 포함. 종료일이 없으면 현직으로 보고 포함)
- 직급: role_level 이 임원급 이상(L1~L3)이거나 등기임원이면 포함.
- 예외: is_highlight=True 인 이력은 기간을 초과해도 별도 목록으로 노출.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core import settings
from core.constants import SET_CAREER_LOOKBACK_YEARS
from data.models import Position

# 임원급 이상으로 보는 role_level 코드 (CodeMaster ROLE_LEVEL)
EXECUTIVE_LEVELS = ("L1", "L2", "L3")


@dataclass
class CareerView:
    recent: list[Position]      # 최근 N년 + 임원급
    highlights: list[Position]  # 기간 초과 주요 경력 (PRD F-03 (3) 예외)
    excluded_count: int         # 규칙에 의해 제외된 건수 (화면에 사유 안내용)


def is_executive(p: Position) -> bool:
    return bool(p.is_registered_officer) or (p.role_level in EXECUTIVE_LEVELS)


def within_lookback(p: Position, lookback_years: int, today: date | None = None) -> bool:
    today = today or date.today()
    cutoff = date(today.year - lookback_years, today.month, today.day)
    if p.end_date is None:
        # 종료일 없음 = 현직으로 간주
        return True
    return p.end_date >= cutoff


def build_view(
    positions: list[Position],
    today: date | None = None,
    lookback_years: int | None = None,
) -> CareerView:
    lookback = lookback_years or settings.get_int(SET_CAREER_LOOKBACK_YEARS, default=10)
    today = today or date.today()

    recent: list[Position] = []
    highlights: list[Position] = []
    excluded = 0

    for p in positions:
        exec_ok = is_executive(p)
        in_window = within_lookback(p, lookback, today)
        if exec_ok and in_window:
            recent.append(p)
        elif p.is_highlight:
            highlights.append(p)
        else:
            excluded += 1

    recent.sort(key=lambda p: (p.start_date or date.min), reverse=True)
    highlights.sort(key=lambda p: (p.start_date or date.min), reverse=True)
    return CareerView(recent=recent, highlights=highlights, excluded_count=excluded)
