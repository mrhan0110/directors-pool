"""S-07 리포트 (PRD 부록 A·B, F-03-6, F-07, F-08-1, F-09-9·17).

검수 완료 + 출력 권한이 있을 때만 생성·다운로드 버튼이 활성화되고, 아니면 비활성 사유를 명시한다.
실제 생성은 reports.builder 가 게이트를 다시 검사한 뒤 수행한다(이중 방어).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import constants as C
from core import pools, state
from core.audit import log_access
from core.guard import confidential_notice, require
from core.ui.components import page_header
from data.repository import get_person_detail, list_person_options
from reports.builder import ExportBlockedError, build_candidate_pdf, build_pool_pdf, check_export

user = require("report")
viewer_label = f"{user.display_name} ({user.email})"

page_header("리포트")
confidential_notice()

tab_person, tab_pool = st.tabs(["사추위 보고용 개인 프로파일", "POOL 리포트"])


def _download(data: bytes, file_name: str, person_ids: list[int], detail: str, key: str) -> None:
    st.download_button(
        "PDF 다운로드",
        data=data,
        file_name=file_name,
        mime="application/pdf",
        key=key,
        on_click=log_access,
        args=(user.user_id, C.ACT_EXPORT),
        kwargs={"page": "report", "target_person_ids": person_ids, "detail": detail},
    )


with tab_person:
    options = list_person_options()
    if not options:
        st.info("후보 데이터가 없습니다.")
    else:
        name_by_id = dict(options)
        picked = st.selectbox(
            "대상 후보", list(name_by_id.keys()), format_func=lambda pid: name_by_id[pid], key="report_person"
        )
        detail = get_person_detail(picked)
        gate = check_export(user.role, [detail.person.profile_status]) if detail else None

        st.subheader("출력 가능 여부")
        if gate and gate.allowed:
            st.success("출력 조건을 충족합니다. (검수 완료 · 출력 권한 보유)")
        elif gate:
            st.error(f"출력할 수 없습니다 — {gate.reason}")

        st.markdown(
            """
            **출력 구성 (PRD 부록 A)**
            1면 ① 기본정보 ② 현재 직업·주요 경력(최근 10년, 임원급) ③ 전문분야 3개 + 근거 ④ 타사 등기임원 현황 ·
            2면 ⑤ 주요 업적 ⑥ 평판 요약(확인된 사실만) ⑦ 선정 고려사항 체크리스트 ⑧ 종합 의견 / 법무 검토 결과 ·
            각주: 항목별 출처(부록 B 형식) · 모든 면: 열람자·일시 워터마크, 대외비 고지
            """
        )
        if detail:
            current = [p for p in detail.positions if p.is_current]
            st.caption(
                f"미리보기 — {detail.person.name_ko} · 현직 "
                + (", ".join(f"{p.org_name} {p.title}" for p in current) or "없음")
                + f" · 타사 등기임원 {sum(1 for d in detail.directorships if d.is_current)}건"
                + f" · 업적 {len(detail.achievements)}건 · 평판 {len(detail.reputations)}건"
            )

        with st.form("report_form"):
            opinion = st.text_area("⑧ 종합 의견 (담당자 작성)")
            legal_review = st.text_area("⑧ 법무 검토 결과")
            submitted = st.form_submit_button(
                "사추위 보고용 PDF 생성",
                disabled=not (gate and gate.allowed),
                help=None if gate and gate.allowed else (gate.reason if gate else None),
            )
        if submitted:
            try:
                with st.spinner("PDF 생성 중…"):
                    state.put(state.K_REPORT, build_candidate_pdf(
                        picked, user.role, viewer_label, opinion=opinion or None, legal_review=legal_review or None
                    ))
                state.put(state.K_REPORT_SIG, f"person:{picked}")
            except ExportBlockedError as exc:
                st.error(f"출력할 수 없습니다 — {exc}")
        if state.get(state.K_REPORT) is not None and state.get(state.K_REPORT_SIG) == f"person:{picked}":
            _download(state.get(state.K_REPORT), f"profile_{picked}_{datetime.now():%Y%m%d_%H%M}.pdf",
                      [picked], "사추위 보고용 프로파일 PDF", key="dl_person")
        st.caption(f"열람자 워터마크: {viewer_label} · 생성 일시 · 대외비")

with tab_pool:
    plist = pools.list_pools()
    if not plist:
        st.info("생성된 POOL 이 없습니다.")
    else:
        pool = st.selectbox("대상 POOL", plist, format_func=lambda p: p.name, key="report_pool")
        members = pools.members(pool.pool_id)
        pool_gate = check_export(user.role, [m.profile_status for m in members]) if members else None
        if not members:
            st.caption("POOL 에 후보가 없습니다.")
        elif pool_gate.allowed:
            st.success(f"출력 조건을 충족합니다. (후보 {len(members)}명 전원 검수 완료)")
        else:
            st.caption(f"출력할 수 없습니다 — {pool_gate.reason}")
        st.caption("구성: POOL 요약표 + 개인별 프로파일 (PRD F-07)")
        if st.button("POOL PDF 생성", disabled=not (pool_gate and pool_gate.allowed),
                     help=pool_gate.reason if pool_gate and not pool_gate.allowed else None):
            try:
                with st.spinner("PDF 생성 중…"):
                    state.put(state.K_REPORT, build_pool_pdf(pool.pool_id, user.role, viewer_label))
                state.put(state.K_REPORT_SIG, f"pool:{pool.pool_id}")
            except (ExportBlockedError, ValueError) as exc:
                st.warning(str(exc))
        if state.get(state.K_REPORT) is not None and state.get(state.K_REPORT_SIG) == f"pool:{pool.pool_id}":
            _download(state.get(state.K_REPORT), f"pool_{pool.pool_id}_{datetime.now():%Y%m%d_%H%M}.pdf",
                      [m.person_id for m in members], f"POOL PDF {pool.pool_id}", key="dl_pool")
