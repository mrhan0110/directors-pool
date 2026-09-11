"""차트 빌더 (PRD 3단계 §E).

표현 전용이다 — 여기서 만드는 표는 이미 계산된 도메인 값(SearchRow, Position, 평판 집계)을
차트가 읽을 수 있는 모양으로만 바꾼다. 판정·집계 로직 자체는 core/ 나머지 모듈에 있다.
"""

from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd

from core import codes as CODES
from core import constants as C

_GENDER_LABEL = {"M": "남", "F": "여"}


def gender_age_dataframe(rows) -> pd.DataFrame:
    """검색 결과의 성별·연령 분포 — 다양성 확인용 (3단계 §E)."""
    bands = CODES.load_codes(C.CODE_AGE_BAND)

    def band_of(age: int | None) -> str:
        if age is None:
            return "미상"
        for b in bands:
            lo, hi = b.extra.get("min"), b.extra.get("max")
            if (lo is None or age >= lo) and (hi is None or age <= hi):
                return b.label
        return "미상"

    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        band = band_of(r.age)
        gender = _GENDER_LABEL.get(r.gender, "미상")
        counts.setdefault(band, {"남": 0, "여": 0, "미상": 0})[gender] += 1

    order = [b.label for b in bands] + ["미상"]
    ordered = {label: counts[label] for label in order if label in counts}
    return pd.DataFrame(ordered).T


_POLARITY_COLOR = {"긍정": "#1E6B34", "중립": "#8A97A6", "부정": "#B3261E"}


def reputation_trend_chart(by_year: dict[int, dict[str, int]]) -> alt.Chart:
    """평판 논조 추이 — 연도 × 긍정/중립/부정 건수. 색은 의미 전달에만 쓴다(디자인 원칙 2)."""
    rows = [
        {"연도": str(year), "논조": polarity, "건수": count}
        for year, counts in sorted(by_year.items())
        for polarity, count in counts.items()
    ]
    df = pd.DataFrame(rows)
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("연도:N", title=None),
            y=alt.Y("건수:Q", title=None),
            color=alt.Color(
                "논조:N",
                scale=alt.Scale(domain=list(_POLARITY_COLOR), range=list(_POLARITY_COLOR.values())),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=["연도", "논조", "건수"],
        )
        .properties(height=220)
    )


def career_timeline_chart(positions) -> alt.Chart | None:
    """경력 타임라인(간트). 진행 중인 직은 오늘까지로 그린다 (3단계 §E)."""
    rows = []
    for pos in positions:
        if pos.start_date is None:
            continue
        rows.append({
            "기관": f"{pos.org_name} · {pos.title}",
            "시작": pos.start_date,
            "종료": pos.end_date or date.today(),
            "구분": "현직" if pos.is_current else "과거",
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    order = df["기관"].tolist()
    return (
        alt.Chart(df)
        .mark_bar(height=14, cornerRadius=2)
        .encode(
            x=alt.X("시작:T", title=None),
            x2="종료:T",
            y=alt.Y("기관:N", sort=order, title=None),
            color=alt.Color(
                "구분:N",
                scale=alt.Scale(domain=["현직", "과거"], range=["#1F4E79", "#B7C4D3"]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=["기관", "시작", "종료", "구분"],
        )
        .properties(height=max(90, 26 * len(rows)))
    )
