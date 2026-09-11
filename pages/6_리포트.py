"""S-07 리포트 (PRD 부록 A·B).

1단계에서 실제로 동작하는 것: 출력 게이트.
검수 미완료 또는 다운로드 권한 없음이면 버튼이 비활성이고 사유를 명시한다.
(PRD F-08-1, F-09-9, F-09-12)
"""

from __future__ import annotations

import streamlit as st

from core import constants as C
from core.guard import confidential_notice, require, stage_notice
from data.repository import get_person_detail, list_person_options
from reports.builder import check_export

user = require("report")

st.title("리포트")
confidential_notice()

options = list_person_options()
if not options:
    st.info("후보 데이터가 없습니다.")
    st.stop()

name_by_id = dict(options)
picked = st.selectbox(
    "사추위 보고용 프로파일 대상", list(name_by_id.keys()), format_func=lambda pid: name_by_id[pid]
)

detail = get_person_detail(picked)
if detail is None:
    st.error("대상을 찾을 수 없습니다.")
    st.stop()

gate = check_export(user.role, [detail.person.profile_status])

st.subheader("출력 가능 여부")
if gate.allowed:
    st.success("출력 조건을 충족합니다.")
else:
    st.error(f"출력할 수 없습니다 — {gate.reason}")

st.button(
    "사추위 보고용 PDF 생성 (2단계)",
    disabled=True,
    help=gate.reason or "PDF 생성은 2단계(I)에서 구현합니다.",
)

st.divider()
st.subheader("출력 템플릿 (PRD 부록 A)")
st.markdown(
    """
    **1면** ① 기본정보 ② 현재 직업 및 경력 타임라인(최근 10년, 임원급) ③ 전문분야 3개 + 근거
    ④ 현 타사 등기임원 현황(회사/직위/선임일/임기만료/잔여임기/출석률)

    **2면** ⑤ 주요 업적 ⑥ 평판 요약 ⑦ 선정 고려사항 체크리스트 ⑧ 종합 의견 / 법무 검토 결과
    · 각주에 항목별 출처 목록 · 하단에 열람자 워터마크와 대외비 표시
    """
)
st.caption(f"열람자 워터마크 예시: {user.display_name} ({user.email}) · 대외비")

stage_notice("PDF/XLSX 생성과 워터마크 삽입은 2단계(I)에서 구현합니다.")
