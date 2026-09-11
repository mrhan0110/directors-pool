"""S-06 검수 (PRD F-08). 1단계는 검수 대기 목록과 3분할 레이아웃 틀만."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from core import constants as C
from core.guard import confidential_notice, require, stage_notice
from data.models import Person
from data.repository import get_person_detail, unreviewed_count
from data.session import session_scope

user = require("review")

st.title("검수")
confidential_notice()

st.metric("검수 대기", f"{unreviewed_count():,}건")
st.caption(
    "검수 완료 전 프로파일은 외부 보고용 출력이 차단됩니다. (PRD F-08-1) "
    "자동 생성 값은 원문 근거와 대조한 뒤 승인합니다."
)

with session_scope() as s:
    pending = list(
        s.execute(
            select(Person.person_id, Person.name_ko)
            .where(Person.profile_status == C.PROFILE_UNREVIEWED)
            .order_by(Person.person_id)
            .limit(200)
        ).all()
    )

if not pending:
    st.success("검수 대기 중인 프로파일이 없습니다.")
    st.stop()

name_by_id = {pid: name for pid, name in pending}
picked = st.selectbox(
    "검수 대상", list(name_by_id.keys()), format_func=lambda pid: name_by_id[pid]
)

detail = get_person_detail(picked)
if detail is None:
    st.error("대상을 찾을 수 없습니다.")
    st.stop()

left, mid, right = st.columns([2, 2, 1])

with left:
    st.subheader("자동 생성 값")
    st.write(f"**성명** {detail.person.name_ko}")
    st.write(f"**출생연도** {detail.person.birth_year or '-'}")
    for e in detail.expertises:
        st.write(f"**전문분야** {e.taxonomy_code} (신뢰도 {e.confidence})")

with mid:
    st.subheader("원문 근거")
    for e in detail.expertises:
        src = detail.sources.get(e.source_id)
        st.write(f"- {e.evidence_snippet}")
        if src:
            st.caption(f"{src.publisher} · {src.url}")

with right:
    st.subheader("판정")
    stage_notice("승인·수정·삭제 처리와 충돌 알림은 2단계(H)에서 구현합니다.")

st.divider()
stage_notice(
    "3분할 검수 워크플로우(승인/수정/삭제, 검수 이력 기록, 자동 갱신 충돌 알림)는 "
    "2단계(H)에서 구현합니다. 현재는 대조 화면 틀만 제공합니다."
)
