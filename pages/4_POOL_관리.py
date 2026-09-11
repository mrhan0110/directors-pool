"""S-05 POOL 관리 (PRD F-07). 1단계는 조회만."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from core import constants as C
from core.guard import confidential_notice, require, stage_notice
from data.models import PoolMember
from data.repository import list_pools, pool_member_counts
from data.session import session_scope

user = require("pool")

st.title("POOL 관리")
confidential_notice()

pools = list_pools()
counts = pool_member_counts()

if not pools:
    st.info("생성된 POOL 이 없습니다.")
    stage_notice("POOL 생성·상태 전이·제외 사유 입력은 2단계(H)에서 구현합니다.")
    st.stop()

pool = st.selectbox(
    "POOL 선택",
    pools,
    format_func=lambda p: f"{p.name} (등록 {counts.get(p.pool_id, 0)}명)",
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("대상 직위", pool.target_position or "-")
c2.metric("등록 인원", f"{counts.get(pool.pool_id, 0)}명")
c3.metric("목표 인원", f"{pool.target_count or '-'}명")
c4.metric("기한", pool.deadline.isoformat() if pool.deadline else "-")

if pool.purpose:
    st.caption(f"목적: {pool.purpose}")

st.divider()
st.subheader("후보 목록")

with session_scope() as s:
    members = list(
        s.execute(
            select(PoolMember)
            .where(PoolMember.pool_id == pool.pool_id)
            .order_by(PoolMember.added_at)
        ).scalars()
    )
    rows = [
        {
            "후보": m.person.name_ko,
            "상태": m.state,
            "사유": m.reason or "-",
            "메모": m.note or "-",
            "등록일": m.added_at.date().isoformat(),
        }
        for m in members
    ]

if rows:
    st.dataframe(rows, hide_index=True, use_container_width=True)
else:
    st.caption("등록된 후보가 없습니다.")

st.caption("상태 전이: " + " → ".join(C.POOL_MEMBER_STATES[:6]) + " / 보류 / 제외")
stage_notice(
    "POOL 생성·후보 추가·상태 전이(제외·보류 시 사유 필수)·칸반 보드는 2단계(H)와 3단계에서 구현합니다."
)
