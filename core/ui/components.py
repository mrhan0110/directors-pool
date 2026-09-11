"""재사용 UI 컴포넌트 (PRD 3단계 §B).

여기 함수는 표현만 담당한다. 도메인 판정(최신성·잔여임기 라벨 등)은 호출부가 core/ 나머지
모듈(core.sources, core.career 등)로 미리 계산해 넘긴다 — core/ui 가 도메인 로직을 중복 구현하지
않기 위해서다.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from core import constants as C

_BADGE_CLASS = {
    C.SCREEN_FAIL: "pool-badge--fail",
    C.SCREEN_WARN: "pool-badge--warn",
    C.SCREEN_PASS: "pool-badge--pass",
    C.SCREEN_INFO: "pool-badge--info",
}


def status_badge(status: str, *, text: str | None = None) -> None:
    """🟢🟡🔴ℹ️ 스크리닝 배지 (디자인 원칙 2 — 색은 의미 전달에만 쓴다)."""
    css_class = _BADGE_CLASS.get(status, "pool-badge--muted")
    label = text if text is not None else C.SCREEN_BADGE.get(status, status)
    st.markdown(f'<span class="pool-badge {css_class}">{label}</span>', unsafe_allow_html=True)


def badge_html(status: str, *, text: str | None = None) -> str:
    """status_badge 의 인라인 삽입용 HTML 문자열 버전(다른 마크다운 조각 안에 섞어 쓸 때)."""
    css_class = _BADGE_CLASS.get(status, "pool-badge--muted")
    label = text if text is not None else C.SCREEN_BADGE.get(status, status)
    return f'<span class="pool-badge {css_class}">{label}</span>'


def source_popover(source, *, outdated: bool = False, label: str = "출처") -> None:
    """값 옆 [출처] 팝오버 — 발행처·문서명·발행일·URL·인용 스니펫 (F-05-1·2, 3단계 §B).

    `source` 가 None 이면 출처 없는 값이 새어나온 것이므로(불변규칙 1) 경고로 명확히 드러낸다.
    """
    if source is None:
        st.error("출처 정보가 없습니다. 표시되어서는 안 되는 데이터입니다. (PRD F-05-1)")
        return
    title = f"📎 {label} · {source.source_tier}등급" + (" · 구 정보" if outdated else "")
    with st.popover(title):
        st.caption(source.citation())
        st.markdown(f"[원문 열기]({source.url})")
        if source.quote_snippet:
            st.caption(f"인용: {source.quote_snippet}")
        if outdated:
            st.caption("⚠ 최신성 기준을 넘은 출처입니다. 최신 자료로 재확인이 필요합니다. (PRD F-05-4)")


def metric_card(label: str, value: str, *, help: str | None = None, delta: str | None = None) -> None:
    """요약 지표 카드. st.metric 을 감싸 표기를 한 곳에서 통일한다."""
    st.metric(label, value, delta=delta, help=help)


def candidate_card(
    title: str,
    *,
    subtitle: str | None = None,
    badges: Sequence[tuple[str, str | None]] = (),
    meta: Sequence[str] = (),
) -> None:
    """후보 요약 카드(POOL 칸반·비교 등에서 사용). badges 는 (status, 텍스트) 목록."""
    badge_row = " ".join(badge_html(status, text=text) for status, text in badges)
    meta_html = "".join(f'<div style="font-size:.82rem;color:var(--pool-muted);">{m}</div>' for m in meta)
    subtitle_html = f'<div style="font-size:.85rem;color:var(--pool-muted);">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="pool-card">
          <div style="display:flex;justify-content:space-between;align-items:start;gap:.5rem;">
            <div style="font-weight:700;">{title}</div>
            <div>{badge_row}</div>
          </div>
          {subtitle_html}
          {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def term_gauge(remaining_months: int | None, alert_months: int, label_text: str, *, max_months: int = 36) -> None:
    """잔여 임기 시각화. alert_months 이내면 경고색, 이미 지났으면 위험색 (F-03-1)."""
    if remaining_months is None:
        st.caption(f"⬜ {label_text}")
        return
    if remaining_months <= 0:
        tone = "danger"
    elif remaining_months <= alert_months:
        tone = "warn"
    else:
        tone = "ok"
    ratio = max(0.0, min(1.0, remaining_months / max_months)) if remaining_months > 0 else 1.0
    prefix = "⚠ " if tone != "ok" else ""
    st.markdown(
        f"""
        <div style="font-size:.85rem;margin-bottom:.15rem;">{prefix}{label_text}</div>
        <div class="pool-term-gauge-track">
          <div class="pool-term-gauge-fill pool-term-gauge-fill--{tone}" style="width:{ratio * 100:.0f}%;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def confidential_banner(text: str) -> None:
    """대외비 고지 배너 (F-09-17). 화면 캡처가 반출돼도 출처를 추적할 수 있도록 눈에 띄게 표시한다."""
    st.markdown(f'<div class="pool-confidential">{text}</div>', unsafe_allow_html=True)


def result_count_banner(total_matched: int, shown: int, capped_by: str | None) -> None:
    """'전체 매칭 N명 중 상위 M명 표시' 배너 (F-01-8, F-02-4). 절단 여부를 놓치지 않도록 강조한다."""
    if total_matched == 0:
        st.warning("조건에 해당하는 후보가 없습니다.")
        return
    truncated = shown < total_matched
    if not truncated:
        st.markdown(
            f'<div class="pool-banner pool-banner--ok">전체 매칭 {total_matched:,}명 전부 표시</div>',
            unsafe_allow_html=True,
        )
        return
    if capped_by == "system":
        detail = f"조건에 해당하는 후보는 {total_matched:,}명이며, 시스템 상한까지만 표시합니다. 조건을 좁혀 주세요."
    elif capped_by == "viewer":
        detail = "외부뷰어 조회 상한이 적용되었습니다."
    else:
        detail = ""
    st.markdown(
        f'<div class="pool-banner pool-banner--warn">전체 매칭 {total_matched:,}명 중 상위 {shown:,}명 표시'
        + (f'<div style="font-weight:400;font-size:.85rem;margin-top:.2rem;">{detail}</div>' if detail else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def page_header(title: str) -> None:
    """공통 헤더 — 시스템명 + 페이지 제목 (3단계 §A)."""
    st.markdown('<div class="pool-system-caption">⚖️ 독립이사 후보자 POOL · 이사회 사무국 전용</div>', unsafe_allow_html=True)
    st.title(title)
