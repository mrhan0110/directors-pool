"""S-01 대시보드 (PRD §9)."""

from __future__ import annotations

import streamlit as st

from core import access, pools, settings, sharing
from core import constants as C
from core.guard import confidential_notice, require
from core.ui.components import page_header
from data import repository

user = require("dashboard")

page_header("대시보드")
confidential_notice()

# 외부뷰어는 공유받은 POOL 만 본다. 전체 후보 통계·명단은 보여주지 않는다 (F-09-12)
if user.is_viewer:
    shared = pools.list_pools(access.allowed_pool_ids(user))
    st.subheader("공유받은 POOL")
    if not shared:
        st.info("현재 열람 가능한 POOL 이 없습니다. 공유 링크가 만료되었거나 회수되었을 수 있습니다.")
    else:
        until = {l.pool_id: l.expires_at for l in sharing.active_links_for(user.email)}
        counts = pools.member_counts()
        for p in shared:
            st.markdown(f"**{p.name}** · 후보 {counts.get(p.pool_id, 0)}명")
            st.caption(f"열람 가능 기한 {until[p.pool_id]:%Y-%m-%d} · 읽기 전용 · 다운로드 불가")
    if user.expires_at:
        st.caption(f"계정 접근 만료일: {user.expires_at.isoformat()}")
    st.stop()

total = repository.person_count()
unreviewed = repository.unreviewed_count()
dist = repository.screening_distribution()

c1, c2, c3, c4 = st.columns(4)
c1.metric("등록 후보", f"{total:,}명")
c2.metric("미검수 프로파일", f"{unreviewed:,}건")
c3.metric("확인 필요", f"{dist[C.SCREEN_WARN]:,}명")
c4.metric("결격 가능", f"{dist[C.SCREEN_FAIL]:,}명")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("임기 만료 임박 (6개월 이내)")
    rows = repository.expiring_directorships(months=6)
    if not rows:
        st.caption("해당 건이 없습니다.")
    else:
        # 담당자가 놓치면 안 되는 정보이므로 가장 급한 건을 색으로 강조한다(디자인 원칙 3).
        alert_months = settings.get_int(C.SET_TERM_ALERT_MONTHS, default=6)

        def _urgency(remaining: int) -> str:
            if remaining <= 0:
                return "🔴 "
            if remaining <= alert_months:
                return "🟡 "
            return ""

        st.dataframe(
            [
                {
                    "후보": person.name_ko,
                    "회사": d.company_name,
                    "직위": d.role_type,
                    "임기 만료": d.term_end_date.isoformat() if d.term_end_date else "-",
                    "잔여": _urgency(remaining) + ("만료" if remaining <= 0 else f"{remaining}개월"),
                }
                for person, d, remaining in rows[:20]
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(f"총 {len(rows)}건 중 상위 20건 표시")

with right:
    st.subheader("POOL 현황")
    pools = repository.list_pools()
    counts = repository.pool_member_counts()
    if not pools:
        st.caption("생성된 POOL 이 없습니다.")
    else:
        for pool in pools:
            st.markdown(
                f"""
                <div class="pool-card">
                  <div style="font-weight:700;">{pool.name}</div>
                  <div style="font-size:.85rem;color:var(--pool-muted);">
                    {pool.target_position or '-'} · 등록 {counts.get(pool.pool_id, 0)}명
                    / 목표 {pool.target_count or '-'}명
                    · 기한 {pool.deadline.isoformat() if pool.deadline else '-'}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.divider()
st.subheader("데이터 정합성 점검")
st.caption("출처 없는 사실 데이터와 근거 없는 전문분야는 0건이어야 합니다. (PRD F-05-1, F-04-2)")
integrity = repository.source_integrity_report()
cols = st.columns(len(integrity))
for col, (label, count) in zip(cols, integrity.items()):
    col.metric(label, f"{count}건", delta=None if count == 0 else "확인 필요")
