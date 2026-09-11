"""전역 CSS 주입 (PRD 3단계 §A).

스타일 코드는 이 파일 한 곳에 모은다(3단계 DoD #5). 페이지마다 흩어놓지 않는다.
`app.py` 가 매 요청 최초 1회 `inject()` 를 호출하면 이후 `st.navigation` 이 위임하는 모든
페이지에 그대로 적용된다(단일 페이지 앱 구조이므로 DOM 이 페이지 전환 사이 유지된다).
"""

from __future__ import annotations

import streamlit as st

# 의미 전달 전용 색상 (디자인 원칙 2 — 그 외에는 무채색 + 포인트 컬러 1개).
# 🔴결격 / 🟡확인필요 / 🟢이슈없음 / 테마 포인트(네이비) / 보조정보.
_CSS = """
<style>
:root {
  --pool-navy: #1F4E79;
  --pool-navy-soft: #E7EEF5;
  --pool-red: #B3261E;
  --pool-red-soft: #FBEAE8;
  --pool-amber: #8A5A00;
  --pool-amber-soft: #FFF3DC;
  --pool-green: #1E6B34;
  --pool-green-soft: #E7F5EA;
  --pool-muted: #5F6B7A;
  --pool-border: #E3E6EA;
}

/* 밀도 — 사내 업무 도구는 스크롤보다 한눈에 보이는 정보량이 중요하다 */
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }
h1 { font-size: 1.55rem !important; margin-bottom: .15rem !important; }
h2, h3 { margin-top: 1.1rem !important; }
[data-testid="stMetricValue"] { font-size: 1.55rem; }

/* 공통 헤더 캡션 (core.ui.components.page_header) */
.pool-system-caption { color: var(--pool-muted); font-size: .82rem; letter-spacing: .02em;
  margin-bottom: .1rem; }

/* 배지 (status_badge) */
.pool-badge { display:inline-flex; align-items:center; gap:.3rem; padding:.18rem .6rem;
  border-radius:999px; font-size:.83rem; font-weight:600; white-space:nowrap; line-height:1.5; }
.pool-badge--fail  { background:var(--pool-red-soft);  color:var(--pool-red); }
.pool-badge--warn  { background:var(--pool-amber-soft); color:var(--pool-amber); }
.pool-badge--pass  { background:var(--pool-green-soft); color:var(--pool-green); }
.pool-badge--info  { background:var(--pool-navy-soft);  color:var(--pool-navy); }
.pool-badge--muted { background:#F0F2F5; color:var(--pool-muted); }

/* 대외비 배너 (confidential_banner) */
.pool-confidential { border-left:3px solid var(--pool-navy); background:var(--pool-navy-soft);
  padding:.5rem .85rem; border-radius:0 6px 6px 0; font-size:.85rem; color:#2B3A4A; margin:.3rem 0 1.1rem; }

/* 결과 절단·강조 배너 (result_count_banner) */
.pool-banner { border-left:3px solid var(--pool-muted); padding:.6rem .9rem; border-radius:0 6px 6px 0;
  font-weight:600; margin-bottom:.6rem; }
.pool-banner--warn { border-left-color:var(--pool-amber); background:var(--pool-amber-soft); color:#5C3D00; }
.pool-banner--ok   { border-left-color:var(--pool-green); background:var(--pool-green-soft); color:#123A20; }
.pool-banner--fail { border-left-color:var(--pool-red);  background:var(--pool-red-soft);  color:#5C1B15; }

/* 잔여임기 게이지 (term_gauge) */
.pool-term-gauge-track { background:#E9ECEF; border-radius:999px; height:8px; width:100%; overflow:hidden; }
.pool-term-gauge-fill { height:100%; border-radius:999px; }
.pool-term-gauge-fill--danger { background:var(--pool-red); }
.pool-term-gauge-fill--warn { background:var(--pool-amber); }
.pool-term-gauge-fill--ok { background:var(--pool-green); }

/* 카드 (candidate_card) */
.pool-card { border:1px solid var(--pool-border); border-radius:10px; padding:.85rem 1rem; background:#fff; }
.pool-card + .pool-card { margin-top: .5rem; }

/* 인쇄 시 사이드바·조작 버튼 숨김, 본문 폭 확장 (디자인 원칙 5) */
@media print {
  [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
  .stButton, .stDownloadButton, .stFormSubmitButton { display:none !important; }
  .block-container { max-width:100% !important; padding-top:0 !important; }
}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
