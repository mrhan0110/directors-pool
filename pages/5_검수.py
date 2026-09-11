"""S-06 검수 (PRD F-08-1 ~ F-08-4).

자동 생성 값 | 원문 근거 | 승인·수정·삭제 3분할. 모든 항목을 처리해야 '검수완료'가 되고,
그 전에는 외부 보고용 출력이 차단된다. 로직은 core/review.py 에 있다.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import codes as CODES
from core import constants as C
from core import review as R
from core.audit import log_access
from core.auth import can_review
from core.guard import confidential_notice, require
from data import repository

user = require("review")
editable = can_review(user.role)

st.title("검수")
confidential_notice()

pending = R.pending_people()
alerts_all = R.open_alerts()
m1, m2 = st.columns(2)
m1.metric("검수 대기 프로파일", f"{len(pending):,}건")
m2.metric("미해결 충돌 알림", f"{len(alerts_all):,}건")
st.caption("검수 완료 전 프로파일은 외부 보고용 출력이 차단됩니다. (PRD F-08-1)")

scope = st.radio("대상", ["미검수", "전체"], horizontal=True)
options = pending if scope == "미검수" else repository.list_person_options()
if not options:
    st.success("검수 대기 중인 프로파일이 없습니다.")
    st.stop()

names = dict(options)
picked = st.selectbox("검수 대상", list(names), format_func=lambda pid: names[pid])
detail = repository.get_person_detail(picked)
if detail is None:
    st.warning("대상을 찾을 수 없습니다.")
    st.stop()
log_access(user.user_id, C.ACT_VIEW, page="review", target_person_ids=[picked])

prog = R.progress(picked)
st.progress(prog.processed / prog.total if prog.total else 1.0,
            text=f"처리 {prog.processed}/{prog.total}건 · 현재 상태 {detail.person.profile_status}")


def summarize(entity: str, row) -> str:
    if entity == "position":
        return f"{row.org_name} {row.title} ({row.start_date or '-'} ~ {row.end_date or ('현재' if row.is_current else '미상')})"
    if entity == "directorship":
        return f"{row.company_name} {row.role_type} (임기 만료 {row.term_end_date or '미상'})"
    if entity == "reputation":
        return f"[{row.polarity}] {row.category or '-'} · {row.summary} ({'확인' if row.verified_yn else '미확인'})"
    if entity == "achievement":
        return f"{row.category or '-'} · {row.description}"
    if entity == "expertise":
        return f"{CODES.label_of(C.CODE_EXPERTISE_L2, row.taxonomy_code)} (신뢰도 {row.confidence})"
    return str(row)  # pragma: no cover


items = R.items_of(picked)
done = R.processed_paths(picked)
rows = []
for entity, row in items:
    eid = getattr(row, R._PK[entity])
    rows.append({"구분": R.ENTITY_LABELS[entity], "내용": summarize(entity, row),
                 "처리": "처리됨" if R._path(entity, eid) in done else "미처리",
                 "수정됨": "예" if row.manually_edited else "-", "_key": (entity, eid)})
st.dataframe([{k: v for k, v in r.items() if k != "_key"} for r in rows], hide_index=True, width="stretch")

# ------------------------------------------------------------------ 3분할 검수 (F-08-2)

if rows:
    keys = [r["_key"] for r in rows]
    labels = {r["_key"]: f"[{r['처리']}] {r['구분']} · {r['내용']}" for r in rows}
    unprocessed = [k for k in keys if labels[k].startswith("[미처리]")]
    key = st.selectbox("검수할 항목", keys, index=keys.index(unprocessed[0]) if unprocessed else 0,
                       format_func=lambda k: labels[k])
    entity, eid = key
    row = next(r for e, r in items if e == entity and getattr(r, R._PK[e]) == eid)

    left, mid, right = st.columns([2, 2, 2])
    with left:
        st.markdown("**자동 생성 값**")
        for field in R.EDITABLE[entity]:
            st.caption(f"{field}: {getattr(row, field)}")
        if entity == "expertise":
            st.caption(f"신뢰도 {row.confidence} · 근거 {row.evidence_count}건 · {'대표' if row.is_primary else '보조'}")
    with mid:
        st.markdown("**원문 근거**")
        src = detail.sources.get(row.source_id)
        if src is None:
            st.error("출처가 없는 항목입니다. 삭제 대상입니다. (PRD F-05-1)")
        else:
            st.caption(src.citation())
            st.markdown(f"[원문 열기]({src.url})")
            if src.quote_snippet:
                st.caption(f"인용: {src.quote_snippet}")
        if entity == "expertise":
            st.caption(f"분류 근거: “{row.evidence_snippet}”")
    with right:
        st.markdown("**승인·수정·삭제**")
        if not editable:
            st.caption("검수 권한이 없습니다.")
        else:
            if st.button("승인", type="primary", width="stretch"):
                R.approve(picked, entity, eid, user.user_id)
                st.rerun()
            with st.form("edit_form", clear_on_submit=True):
                fields = R.EDITABLE[entity]
                field = st.selectbox("수정 항목", list(fields))
                kind = fields[field]
                current = getattr(row, field)
                if kind == "date":
                    value = st.date_input("새 값", value=current if isinstance(current, date) else None)
                elif kind == "float":
                    value = st.number_input("새 값 (0~1)", min_value=0.0, max_value=1.0,
                                            value=float(current or 0.0), step=0.01)
                elif kind == "bool":
                    value = st.checkbox("새 값", value=bool(current))
                else:
                    value = st.text_input("새 값", value=current or "")
                if st.form_submit_button("수정 저장"):
                    try:
                        R.edit(picked, entity, eid, field, value, user.user_id)
                        st.rerun()
                    except (ValueError, LookupError) as exc:
                        st.warning(str(exc))
            with st.form("delete_form", clear_on_submit=True):
                reason = st.text_input("삭제 사유 (필수)")
                if st.form_submit_button("삭제"):
                    try:
                        R.delete(picked, entity, eid, user.user_id, reason)
                        st.rerun()
                    except (ValueError, LookupError) as exc:
                        st.warning(str(exc))

# ------------------------------------------------------------------ 충돌 알림 (F-08-4)

alerts = R.open_alerts(picked)
if alerts:
    st.divider()
    st.subheader(f"충돌 알림 {len(alerts)}건")
    st.caption("검수자가 수정한 항목을 자동 갱신이 다른 값으로 바꾸려 했습니다. 어느 값을 쓸지 정하세요.")
    for q in alerts:
        pl = q.payload or {}
        st.markdown(f"**{R.ENTITY_LABELS.get(pl.get('entity'), pl.get('entity'))} · {pl.get('field')}** — "
                    f"현재(검수자 수정) '{pl.get('current_value')}' / 새 수집 값 '{pl.get('new_value')}'")
        if editable:
            a1, a2 = st.columns(2)
            if a1.button("새 값 반영", key=f"accept_{q.id}", width="stretch"):
                R.resolve_alert(q.id, user.user_id, accept_new=True)
                st.rerun()
            if a2.button("현재 값 유지", key=f"keep_{q.id}", width="stretch"):
                R.resolve_alert(q.id, user.user_id, accept_new=False)
                st.rerun()

# ------------------------------------------------------------------ 완료·재검수

st.divider()
if editable:
    if detail.person.profile_status == C.PROFILE_REVIEWED:
        with st.form("reopen", clear_on_submit=True):
            reason = st.text_input("재검수 사유 (필수)")
            if st.form_submit_button("재검수로 되돌리기"):
                try:
                    R.reopen(picked, user.user_id, reason)
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
    else:
        blocked = not prog.done or bool(alerts)
        if st.button("검수 완료", type="primary", disabled=blocked,
                     help="모든 항목을 처리하고 충돌 알림을 해결해야 완료할 수 있습니다."):
            try:
                R.complete(picked, user.user_id)
                st.success("검수를 완료했습니다. 이제 외부 보고용 출력이 가능합니다.")
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
        if blocked:
            st.caption(f"미처리 {prog.total - prog.processed}건 · 충돌 알림 {len(alerts)}건")

hist = R.history(picked)
if hist:
    with st.expander(f"검수 이력 {len(hist)}건 (PRD F-08-3)"):
        st.dataframe(
            [{"일시": h.reviewed_at.strftime("%Y-%m-%d %H:%M"), "항목": h.field_path, "처리": h.action,
              "이전": h.before_value or "-", "이후": h.after_value or "-", "검수자": h.reviewer_id or "-"}
             for h in hist[:100]],
            hide_index=True,
            width="stretch",
        )
