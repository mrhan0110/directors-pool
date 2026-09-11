"""S-05 POOL 관리 (PRD F-07).

POOL 생성·수정·삭제, 후보 추가·상태 전이(보류·제외 사유 필수), 코멘트 타임라인, POOL 단위 XLSX.
로직은 core/pools.py 에 있고 이 파일은 표현만 담당한다.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import access, pools, state
from core import constants as C
from core.audit import log_access
from core.auth import can_edit_pool
from core.guard import confidential_notice, require
from data import repository
from reports import exports
from reports.builder import check_export
from reports.xlsx import ExportMeta, build_table_xlsx

user = require("pool")
editable = can_edit_pool(user.role)

st.title("POOL 관리")
confidential_notice()

# ------------------------------------------------------------------ 새 POOL

if editable:
    with st.expander("새 POOL 만들기"):
        with st.form("pool_create", clear_on_submit=True):
            name = st.text_input("POOL 명칭 *")
            purpose = st.text_input("목적")
            target_position = st.text_input("대상 직위")
            c1, c2 = st.columns(2)
            target_count = c1.number_input("목표 인원", min_value=0, step=1, value=0)
            deadline = c2.date_input("기한", value=None)
            memo = st.text_area("메모")
            if st.form_submit_button("생성"):
                try:
                    pools.create_pool(name, user.user_id, purpose=purpose, target_position=target_position,
                                      target_count=int(target_count) or None, deadline=deadline, memo=memo)
                    st.success("POOL 을 만들었습니다.")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))

# 외부뷰어는 공유받은 POOL 만 (F-09-12). 범위는 매 요청 DB 에서 다시 계산한다.
plist = pools.list_pools(access.allowed_pool_ids(user))
counts = pools.member_counts()
if not plist:
    st.info("열람 가능한 POOL 이 없습니다." if user.is_viewer else "생성된 POOL 이 없습니다.")
    st.stop()

pool_ids = [p.pool_id for p in plist]
preferred = state.get(state.K_SELECTED_POOL)
pool = st.selectbox(
    "POOL 선택",
    plist,
    index=pool_ids.index(preferred) if preferred in pool_ids else 0,
    format_func=lambda p: f"{p.name} (등록 {counts.get(p.pool_id, 0)}명)",
    key="pool_select",
)
state.put(state.K_SELECTED_POOL, pool.pool_id)
if user.is_viewer:
    st.caption("공유받은 POOL 입니다. 읽기 전용이며 다운로드할 수 없습니다.")
log_access(user.user_id, C.ACT_VIEW, page="pool", detail=f"pool={pool.pool_id}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("대상 직위", pool.target_position or "-")
c2.metric("등록 인원", f"{counts.get(pool.pool_id, 0)}명")
c3.metric("목표 인원", f"{pool.target_count or '-'}명")
c4.metric("기한", pool.deadline.isoformat() if pool.deadline else "-")
if pool.purpose:
    st.caption(f"목적: {pool.purpose}")

if editable:
    with st.expander("POOL 정보 수정·삭제"):
        with st.form("pool_edit"):
            e_name = st.text_input("POOL 명칭 *", value=pool.name)
            e_purpose = st.text_input("목적", value=pool.purpose or "")
            e_target = st.text_input("대상 직위", value=pool.target_position or "")
            e1, e2 = st.columns(2)
            e_count = e1.number_input("목표 인원", min_value=0, step=1, value=pool.target_count or 0)
            e_deadline = e2.date_input("기한", value=pool.deadline)
            if st.form_submit_button("수정 저장"):
                try:
                    pools.update_pool(pool.pool_id, user.user_id, name=e_name, purpose=e_purpose or None,
                                      target_position=e_target or None, target_count=int(e_count) or None,
                                      deadline=e_deadline)
                    st.success("수정했습니다.")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
        confirm = st.checkbox("이 POOL 을 삭제합니다 (되돌릴 수 없음)")
        if st.button("POOL 삭제", disabled=not confirm):
            try:
                pools.delete_pool(pool.pool_id, user.user_id)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))

st.divider()

# ------------------------------------------------------------------ 후보 보드

st.subheader("후보 상태 보드")
st.caption("상태 흐름: " + " → ".join(pools.FLOW) + " / 보류 / 제외 (보류·제외는 사유 필수)")
members = pools.members(pool.pool_id)
if not members:
    st.caption("등록된 후보가 없습니다. 후보 검색 화면에서 선택해 저장하거나 아래에서 추가하세요.")
else:
    states = list(pools.FLOW) + [pools.HOLD, pools.EXCLUDED]
    cols = st.columns(len(states))
    for col, s in zip(cols, states):
        in_state = [m for m in members if m.state == s]
        col.markdown(f"**{s}** ({len(in_state)})")
        for m in in_state:
            col.caption(m.name_ko + (" · 검수완료" if m.profile_status == C.PROFILE_REVIEWED else " · 미검수"))
    st.dataframe(
        [
            {"후보": m.name_ko, "상태": m.state, "사유": m.reason or "-", "메모": m.note or "-",
             "검수": m.profile_status, "등록일": m.added_at.date().isoformat()}
            for m in members
        ],
        hide_index=True,
        width="stretch",
    )

if editable and members:
    with st.form("state_change", clear_on_submit=True):
        st.markdown("**상태 변경**")
        by_id = {m.person_id: m for m in members}
        pid = st.selectbox("후보", list(by_id), format_func=lambda i: f"{by_id[i].name_ko} ({by_id[i].state})")
        to_state = st.selectbox("변경할 상태", states)
        reason = st.text_area("사유 (보류·제외 시 필수)")
        if st.form_submit_button("변경"):
            try:
                pools.change_state(pool.pool_id, pid, to_state, user.user_id, reason=reason,
                                   expected_state=by_id[pid].state)
                st.success("변경했습니다.")
                st.rerun()
            except (ValueError, LookupError, pools.ConcurrentUpdateError) as exc:
                st.warning(str(exc))

if editable:
    with st.expander("후보 추가"):
        existing = {m.person_id for m in members}
        options = [(pid, name) for pid, name in repository.list_person_options() if pid not in existing]
        names = dict(options)
        picked = st.multiselect("추가할 후보", list(names), format_func=lambda i: names[i], placeholder="후보 선택")
        if st.button("추가", disabled=not picked):
            added, _ = pools.add_members(pool.pool_id, picked, user.user_id)
            st.success(f"{added}명을 추가했습니다.")
            st.rerun()

# ------------------------------------------------------------------ 코멘트·이력 (F-07)

st.divider()
st.subheader("코멘트·변경 이력")
if editable:
    with st.form("comment", clear_on_submit=True):
        text = st.text_area("코멘트")
        if st.form_submit_button("등록"):
            try:
                pools.add_comment(pool.pool_id, text, user.user_id)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
events = pools.timeline(pool.pool_id)
names_all = dict(access.filter_person_options(user, repository.list_person_options()))
if events:
    st.dataframe(
        [
            {
                "일시": e.occurred_at.strftime("%Y-%m-%d %H:%M"),
                "구분": e.event,
                "후보": names_all.get(e.person_id, "-") if e.person_id else "-",
                "변경": f"{e.from_state or ''} → {e.to_state}" if e.to_state else "-",
                "내용": e.comment or "-",
                "작성자": e.user_id or "-",
            }
            for e in events[:100]
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.caption("이력이 없습니다.")

# ------------------------------------------------------------------ POOL 단위 출력 (F-07, F-08-1)

st.divider()
st.subheader("POOL 단위 출력")
ids = [m.person_id for m in members]
gate = check_export(user.role, [m.profile_status for m in members])
if not ids:
    st.caption("출력할 후보가 없습니다.")
elif not gate.allowed:
    st.button("POOL XLSX 내보내기", disabled=True, help=gate.reason, key="pool_xlsx_blocked")
    st.caption(f"출력할 수 없습니다 — {gate.reason}")
else:
    meta = ExportMeta(
        title=f"POOL 요약 — {pool.name}",
        viewer_label=f"{user.display_name} ({user.email})",
        generated_at=datetime.now(),
        conditions=[f"POOL: {pool.name}", f"대상 직위: {pool.target_position or '-'}"],
        shown=len(ids),
    )
    st.download_button(
        "POOL XLSX 다운로드",
        data=build_table_xlsx(exports.candidate_rows(ids), meta, sheet_title="POOL 후보"),
        file_name=f"pool_{pool.pool_id}_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click=log_access,
        args=(user.user_id, C.ACT_EXPORT),
        kwargs={"page": "pool", "target_person_ids": ids, "detail": f"pool xlsx {pool.pool_id}"},
    )
    st.caption("개인별 사추위 보고용 PDF 는 리포트 화면에서 출력합니다.")
