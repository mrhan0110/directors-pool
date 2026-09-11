"""S-08 관리자 (PRD §9, F-01-7). 관리자 역할만 접근 가능."""

from __future__ import annotations

import streamlit as st

from core import codes as CODES, constants as C, settings
from core.audit import history_of, log_change
from core.guard import confidential_notice, require
from data.repository import list_users, recent_access_logs, source_integrity_report

user = require("admin")

st.title("관리자")
confidential_notice()

tab_codes, tab_settings, tab_users, tab_logs, tab_integrity = st.tabs(
    ["드롭다운 코드", "운영 파라미터", "사용자·권한", "접근 로그", "데이터 정합성"]
)

# ------------------------------------------------------------------ 드롭다운 코드 (F-01-7)

with tab_codes:
    st.caption("검색 드롭다운 선택지는 모두 이 테이블에서 로드됩니다. 코드는 삭제하지 않고 비활성화합니다"
               "(과거 데이터가 참조할 수 있어서입니다).")
    categories = CODES.all_categories()
    category = st.selectbox("카테고리", categories, key="admin_code_category")
    rows = CODES.load_all(category) if category else []
    st.dataframe(
        [
            {
                "코드": r.code,
                "표시명": r.label,
                "상위코드": r.parent_code or "-",
                "순서": r.sort_order,
                "활성": "Y" if r.is_active else "N",
                "파라미터": str(r.extra) if r.extra else "-",
            }
            for r in rows
        ],
        hide_index=True,
        width="stretch",
    )

    col_edit, col_add = st.columns(2)
    with col_edit:
        st.markdown("**기존 코드 수정**")
        if rows:
            with st.form("admin_code_edit_form"):
                target = st.selectbox(
                    "코드 선택", rows, format_func=lambda r: f"{r.code} — {r.label}",
                    key="admin_code_edit_target",
                )
                new_label = st.text_input("표시명", value=target.label, key="admin_code_edit_label")
                new_order = st.number_input(
                    "정렬 순서", value=target.sort_order, step=1, key="admin_code_edit_order"
                )
                new_active = st.checkbox("활성", value=target.is_active, key="admin_code_edit_active")
                if st.form_submit_button("저장", type="primary"):
                    try:
                        CODES.update_code(
                            target.id, label=new_label, sort_order=int(new_order),
                            is_active=new_active, user_id=user.user_id,
                        )
                        st.success("코드를 수정했습니다.")
                        st.rerun()
                    except (ValueError, LookupError) as exc:
                        st.warning(str(exc))
        else:
            st.caption("이 카테고리에 코드가 없습니다.")

    with col_add:
        st.markdown("**새 코드 추가**")
        with st.form("admin_code_add_form", clear_on_submit=True):
            new_code = st.text_input("코드", key="admin_code_new_code", placeholder="예: EXP_ESG_04")
            add_label = st.text_input("표시명", key="admin_code_new_label")
            parent = st.text_input("상위코드 (선택)", key="admin_code_new_parent")
            add_order = st.number_input("정렬 순서", value=0, step=1, key="admin_code_new_order")
            if st.form_submit_button("추가"):
                try:
                    CODES.create_code(
                        category, new_code, add_label, parent_code=parent, sort_order=int(add_order),
                        user_id=user.user_id,
                    )
                    st.success(f"코드를 추가했습니다: {new_code}")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))

    with st.expander("변경 이력"):
        code_history = history_of("code", prefix=f"{category}/") if category else []
        if code_history:
            st.dataframe(
                [
                    {"시각": h.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), "대상": h.entity_id,
                     "행위": h.action, "내용": h.detail or "-"}
                    for h in code_history
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("변경 이력이 없습니다.")

# ------------------------------------------------------------------ 운영 파라미터 (불변규칙 4)

with tab_settings:
    st.caption(
        "법령 연동 임계값은 코드에 하드코딩하지 않고 여기서 관리합니다. "
        "법 개정 시 이 값을 먼저 갱신하세요. (PRD §5 상단)"
    )
    items = settings.list_all()
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
        width="stretch",
    )
    st.warning(
        "겸직 한도·재직 연수 상한·냉각기간은 최신 상법 및 시행령으로 법무 확인이 필요한 "
        "미결 사항입니다. (PRD §14-5)",
        icon="⚠️",
    )

    st.markdown("**값 수정**")
    by_key = {it.key: it for it in items}
    with st.form("admin_setting_edit_form"):
        target_key = st.selectbox("설정 키", list(by_key.keys()), key="admin_setting_key")
        target_item = by_key[target_key]
        st.caption(target_item.description or "")
        if target_item.legal_basis:
            st.caption(f"⚠️ 법령 근거: {target_item.legal_basis}")
        new_value = st.text_input("새 값", value=target_item.value, key="admin_setting_value")
        if st.form_submit_button("저장", type="primary"):
            try:
                before = settings.set_value(target_key, new_value, user_id=user.user_id)
                log_change(user.user_id, "setting", "update", target_key, f"{before} → {new_value.strip()}")
                st.success("설정값을 변경했습니다.")
                st.rerun()
            except (KeyError, ValueError) as exc:
                st.warning(str(exc))

    with st.expander("변경 이력"):
        setting_history = history_of("setting")
        if setting_history:
            st.dataframe(
                [
                    {"시각": h.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), "키": h.entity_id,
                     "내용": h.detail or "-"}
                    for h in setting_history
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("변경 이력이 없습니다.")

# ------------------------------------------------------------------ 사용자·권한

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
        width="stretch",
    )
    st.caption("역할별 권한: " + " / ".join(f"{k}={v}" for k, v in C.ROLE_DESCRIPTIONS.items()))
    st.caption(
        "사용자 추가·역할 변경은 SSO(OIDC) 연동 완료 후 IdP 그룹 매핑으로 관리합니다 (PRD F-09-10, §14 결정 대기). "
        "현재는 mock 인증 계정 목록을 조회만 합니다."
    )

# ------------------------------------------------------------------ 접근 로그 (F-09-22)

with tab_logs:
    st.caption("로그인·조회·검색·다운로드·공유 행위를 애플리케이션 레벨에서 적재합니다. (PRD F-09-22)")
    logs = recent_access_logs(200)
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
            width="stretch",
        )
        st.caption("최근 200건")
    else:
        st.caption("기록된 로그가 없습니다.")

# ------------------------------------------------------------------ 데이터 정합성

with tab_integrity:
    st.caption("전부 0건이어야 정상입니다.")
    report = source_integrity_report()
    for label, count in report.items():
        if count == 0:
            st.success(f"{label}: {count}건")
        else:
            st.error(f"{label}: {count}건 — 즉시 확인이 필요합니다.")
