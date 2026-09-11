"""core/ui/components.py — 재사용 컴포넌트 (PRD 3단계 §B)."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HARNESS = PROJECT_ROOT / "tests" / "_harness_ui_components.py"


def _run():
    at = AppTest.from_file(str(HARNESS), default_timeout=30)
    return at.run()


def _all_markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_harness_renders_without_exception():
    at = _run()
    assert not at.exception


def test_page_header_shows_title_and_system_caption():
    at = _run()
    assert at.title[0].value == "헤더 테스트"
    assert "독립이사 후보자 POOL" in _all_markdown(at)


def test_confidential_banner_renders_styled_div():
    at = _run()
    html = _all_markdown(at)
    assert "pool-confidential" in html
    assert "대외비 테스트 문구" in html


def test_status_badge_maps_each_screening_result_to_its_css_class():
    at = _run()
    html = _all_markdown(at)
    assert "pool-badge--fail" in html
    assert "pool-badge--warn" in html
    assert "pool-badge--pass" in html
    assert "pool-badge--info" in html


def test_candidate_card_renders_title_subtitle_and_meta():
    at = _run()
    html = _all_markdown(at)
    assert "가상001 김서연" in html
    assert "가상전자 · 사외이사" in html
    assert "잔여임기 3개월" in html
    assert "pool-card" in html


def test_term_gauge_tone_by_remaining_months():
    at = _run()
    html = _all_markdown(at)
    assert "pool-term-gauge-fill--warn" in html   # 3개월 남음(alert=6) → 경고
    assert "pool-term-gauge-fill--danger" in html  # 이미 만료 → 위험
    # 미상(None)은 게이지 대신 caption 으로 빠진다
    assert any("임기 미상" in c.value for c in at.caption)


def test_result_count_banner_branches():
    at = _run()
    html = _all_markdown(at)
    # 0건은 st.warning 으로 (배너 div 가 아님)
    assert any("조건에 해당하는 후보가 없습니다" in w.value for w in at.warning)
    assert "전체 매칭 50명 전부 표시" in html and "pool-banner--ok" in html
    assert "전체 매칭 500명 중 상위 100명 표시" in html and "pool-banner--warn" in html
    assert "외부뷰어 조회 상한이 적용되었습니다" in html


def test_source_popover_missing_source_shows_error():
    at = _run()
    assert any("출처 정보가 없습니다" in e.value for e in at.error)


def test_source_popover_renders_for_valid_source():
    at = _run()
    pops = at.get("popover")
    assert len(pops) >= 2  # 정상 출처 1개 + 구정보 출처 1개
    labels = [p.proto.popover.label for p in pops]
    assert any("A등급" in lbl for lbl in labels)
    assert any("구 정보" in lbl for lbl in labels)
