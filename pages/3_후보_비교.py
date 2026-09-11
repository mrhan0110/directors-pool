"""S-03 후보 비교 (PRD F-02-1). 최대 4명."""

from __future__ import annotations

import streamlit as st

from core import codes as CODES, constants as C, scoring, state
from core.audit import log_access
from core.guard import confidential_notice, require, stage_notice
from data import repository

user = require("compare")

st.title("후보 비교")
confidential_notice()

basket = state.compare_basket()
options = repository.list_person_options()
name_by_id = dict(options)

picked = st.multiselect(
    "비교할 후보 (최대 4명)",
    [pid for pid, _ in options],
    default=[pid for pid in basket if pid in name_by_id][:4],
    format_func=lambda pid: name_by_id[pid],
    max_selections=4,
    placeholder="검색 화면에서 담거나 여기서 직접 선택하세요",
)
state.put(state.K_COMPARE_BASKET, picked)

if not picked:
    st.info("비교할 후보를 선택하세요.")
    st.stop()

log_access(user.user_id, C.ACT_VIEW, page="compare", target_person_ids=picked)

details = [repository.get_person_detail(pid) for pid in picked]
details = [d for d in details if d is not None]

rows = {
    "성별": [],
    "나이": [],
    "현재 직업": [],
    "전문분야": [],
    "타사 등기임원": [],
    "스크리닝": [],
    "적합도": [],
    "검수 상태": [],
}

for d in details:
    p = d.person
    current = next((pos for pos in d.positions if pos.is_current), None)
    exp_labels = [
        CODES.label_of(C.CODE_EXPERTISE_L2, e.taxonomy_code)
        for e in d.expertises
        if e.is_primary
    ][:3]
    worst = max(
        (s.result for s in d.screenings), key=lambda r: C.SCREEN_ORDER.get(r, 0), default=C.SCREEN_PASS
    )
    rows["성별"].append({"M": "남성", "F": "여성"}.get(p.gender, "-"))
    rows["나이"].append(f"만 {p.age()}세" if p.age() else "-")
    rows["현재 직업"].append(f"{current.org_name} {current.title}" if current else "-")
    rows["전문분야"].append(", ".join(exp_labels) or "-")
    rows["타사 등기임원"].append(f"{sum(1 for x in d.directorships if x.is_current)}개")
    rows["스크리닝"].append(C.SCREEN_BADGE[worst])
    rows["적합도"].append(scoring.NOT_IMPLEMENTED_LABEL)
    rows["검수 상태"].append(p.profile_status)

table = [{"항목": key, **{d.person.name_ko: val for d, val in zip(details, vals)}}
         for key, vals in rows.items()]
st.dataframe(table, hide_index=True, use_container_width=True)

stage_notice("차이 값 강조·항목 확장 비교는 3단계(C)에서 구현합니다.")
