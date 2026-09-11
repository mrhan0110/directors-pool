"""S-08 관리자 (PRD §9). 관리자 역할만 접근 가능."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from core import codes as CODES, constants as C, settings
from core.guard import confidential_notice, require, stage_notice
from data.models import AccessLog, CodeMaster
from data.repository import list_users, source_integrity_report
from data.session import session_scope

user = require("admin")

st.title("관리자")
confidential_notice()

tab_codes, tab_settings, tab_users, tab_logs, tab_integrity = st.tabs(
    ["드롭다운 코드", "운영 파라미터", "사용자·권한", "접근 로그", "데이터 정합성"]
)

with tab_codes:
    st.caption("검색 드롭다운 선택지는 모두 이 테이블에서 로드됩니다. (PRD F-01-7)")
    with session_scope() as s:
        categories = sorted(
            {row for row in s.execute(select(CodeMaster.category)).scalars()}
        )
    category = st.selectbox("카테고리", categories)
    rows = CODES.load_codes(category)
    st.dataframe(
        [
            {
                "코드": r.code,
                "표시명": r.label,
                "상위코드": r.parent_code or "-",
                "순서": r.sort_order,
                "파라미터": str(r.extra) if r.extra else "-",
            }
            for r in rows
        ],
        hide_index=True,
        use_container_width=True,
    )
    stage_notice("코드 추가·수정과 변경 이력 관리는 2단계에서 구현합니다.")

with tab_settings:
    st.caption(
        "법령 연동 임계값은 코드에 하드코딩하지 않고 여기서 관리합니다. "
        "법 개정 시 이 값을 먼저 갱신하세요. (PRD §5 상단)"
    )
    from data.models import AppSetting

    with session_scope() as s:
        items = list(s.execute(select(AppSetting).order_by(AppSetting.key)).scalars())
    st.dataframe(
        [
            {
                "키": it.key,
                "값": it.value,
                "설명": it.description or "-",
                "법령 근거": it.legal_basis or "-",
                "최종 변경": it.updated_at.date().isoformat(),
            }
            for it in items
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.warning(
        "겸직 한도·재직 연수 상한·냉각기간은 최신 상법 및 시행령으로 법무 확인이 필요한 "
        "미결 사항입니다. (PRD §14-5)",
        icon="⚠️",
    )
    stage_notice("값 수정 UI 와 변경 이력 기록은 2단계에서 구현합니다.")

with tab_users:
    st.dataframe(
        [
            {
                "ID": u.user_id,
                "이메일": u.email,
                "이름": u.display_name,
                "역할": u.role,
                "활성": "Y" if u.is_active else "N",
                "접근 만료": u.expires_at.isoformat() if u.expires_at else "-",
                "최근 로그인": u.last_login_at.date().isoformat() if u.last_login_at else "-",
            }
            for u in list_users()
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.caption("역할별 권한: " + " / ".join(f"{k}={v}" for k, v in C.ROLE_DESCRIPTIONS.items()))

with tab_logs:
    st.caption("로그인·조회·검색·다운로드·공유 행위를 애플리케이션 레벨에서 적재합니다. (PRD F-09-22)")
    with session_scope() as s:
        logs = list(
            s.execute(
                select(AccessLog).order_by(AccessLog.occurred_at.desc()).limit(200)
            ).scalars()
        )
    if logs:
        st.dataframe(
            [
                {
                    "시각": lg.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "사용자": lg.user_id,
                    "페이지": lg.page or "-",
                    "액션": lg.action,
                    "대상 후보": ", ".join(map(str, lg.target_person_ids)) or "-",
                    "상세": lg.detail or "-",
                }
                for lg in logs
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption("최근 200건")
    else:
        st.caption("기록된 로그가 없습니다.")

with tab_integrity:
    st.caption("전부 0건이어야 정상입니다.")
    report = source_integrity_report()
    for label, count in report.items():
        if count == 0:
            st.success(f"{label}: {count}건")
        else:
            st.error(f"{label}: {count}건 — 즉시 확인이 필요합니다.")
