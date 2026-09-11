"""core/ui/charts.py — 차트 데이터 빌더 (PRD 3단계 §E)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from core.ui import charts as UI_CHARTS


def _row(gender, age):
    return SimpleNamespace(gender=gender, age=age)


def test_gender_age_dataframe_buckets_by_band():
    rows = [_row("M", 52), _row("F", 52), _row("M", 45), _row("F", None)]
    df = UI_CHARTS.gender_age_dataframe(rows)
    assert df.loc["50~54세", "남"] == 1
    assert df.loc["50~54세", "여"] == 1
    assert df.loc["49세 이하", "남"] == 1
    assert df.loc["미상", "여"] == 1


def test_gender_age_dataframe_empty_rows():
    df = UI_CHARTS.gender_age_dataframe([])
    assert df.empty


def test_reputation_trend_chart_carries_expected_rows():
    chart = UI_CHARTS.reputation_trend_chart({2024: {"긍정": 1, "중립": 0, "부정": 2}})
    data = chart.data
    assert set(data["논조"]) == {"긍정", "중립", "부정"}
    assert int(data.loc[data["논조"] == "부정", "건수"].iloc[0]) == 2


def test_career_timeline_chart_none_when_no_dated_positions():
    assert UI_CHARTS.career_timeline_chart([]) is None
    assert UI_CHARTS.career_timeline_chart([SimpleNamespace(start_date=None)]) is None


def test_career_timeline_chart_builds_rows_for_current_and_past():
    positions = [
        SimpleNamespace(org_name="가상전자", title="상무", start_date=date(2020, 1, 1),
                        end_date=None, is_current=True),
        SimpleNamespace(org_name="가상화학", title="이사", start_date=date(2010, 1, 1),
                        end_date=date(2015, 1, 1), is_current=False),
    ]
    chart = UI_CHARTS.career_timeline_chart(positions)
    assert chart is not None
    data = chart.data
    assert len(data) == 2
    assert set(data["구분"]) == {"현직", "과거"}
    current_row = data[data["구분"] == "현직"].iloc[0]
    assert current_row["종료"] == date.today()
