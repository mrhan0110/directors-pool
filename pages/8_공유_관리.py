"""S-09 공유 관리 (PRD F-09-14 ~ F-09-18).

발급(수신자·목적·범위·만료일 필수) / 발급 현황과 상태 / 즉시 회수 / 접속 이력.
링크 원문은 발급 직후 한 번만 보여준다(DB 에는 해시만 저장). 로직은 core/sharing.py.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core import constants as C
from core import pools, settings, sharing, state
from core.guard import confidential_notice, require

user = require("share")

st.title("공유 관리")
confidential_notice()

default_days = settings.get_int(C.SET_SHARE_LINK_DEFAULT_DAYS)
max_days = settings.get_int(C.SET_SHARE_LINK_MAX_DAYS)
st.info(
    f"""
    공유 링크 정책
    - 링크는 **POOL + 수신자 이메일 + 만료일시**에 바인딩되며, 토큰만으로는 열람할 수 없습니다(수신자 계정 로그인 필수).
    - 수신자는 지정된 POOL 만 읽기 전용으로 보며 다운로드할 수 없습니다.
    - 기본 만료 {default_days}일, 최대 {max_days}일 (관리자 설정).
    - 발급·접속·회수 이력은 모두 감사로그에 남고, 회수하면 다음 요청부터 즉시 차단됩니다.
    """,
    icon="🔐",
)

# ------------------------------------------------------------------ 발급 (F-09-14·15)

plist = pools.list_pools()
if not plist:
    st.caption("공유할 POOL 이 없습니다.")
else:
    with st.form("share_issue", clear_on_submit=True):
        pool = st.selectbox("공유할 POOL *", plist, format_func=lambda p: p.name)
        email = st.text_input("수신자 이메일 *", placeholder="수신자의 시스템 계정 이메일")
        purpose = st.text_area("공유 목적 *")
        st.caption("범위: POOL 단위 · 읽기 전용 · 다운로드 불가")
        today = date.today()
        expires_on = st.date_input(
            "만료일 *",
            value=sharing.default_expiry(today),
            min_value=today + timedelta(days=1),
            max_value=sharing.max_expiry(today),
        )
        submitted = st.form_submit_button("공유 링크 발급", type="primary")
    if submitted:
        try:
            issued = sharing.issue_link(pool.pool_id, user.user_id, email, purpose, expires_on)
            state.put(state.K_ISSUED_LINK, (issued.share_id, issued.url))
        except (ValueError, LookupError) as exc:
            st.warning(str(exc))

issued_now = state.get(state.K_ISSUED_LINK)
if issued_now:
    share_id, url = issued_now
    st.success(f"공유 링크를 발급했습니다 (ID {share_id}). 아래 주소는 지금 한 번만 표시됩니다.")
    st.code(url, language=None)
    st.caption("수신자는 이 링크로 접속한 뒤 본인 계정으로 로그인해야 열람할 수 있습니다.")
    st.session_state.pop(state.K_ISSUED_LINK, None)

# ------------------------------------------------------------------ 발급 현황 (F-09-16)

st.divider()
st.subheader("발급 현황")
links = sharing.list_links()
pool_names = {p.pool_id: p.name for p in plist}
if not links:
    st.caption("발급된 공유 링크가 없습니다.")
else:
    statuses = {lk.share_id: sharing.status_of(lk) for lk in links}
    st.dataframe(
        [
            {
                "ID": lk.share_id,
                "상태": statuses[lk.share_id],
                "POOL": pool_names.get(lk.pool_id, lk.pool_id),
                "수신자": lk.recipient_email,
                "목적": lk.purpose,
                "범위": "읽기 전용",
                "발급": lk.issued_at.strftime("%Y-%m-%d"),
                "만료": lk.expires_at.strftime("%Y-%m-%d"),
                "회수": lk.revoked_at.strftime("%Y-%m-%d %H:%M") if lk.revoked_at else "-",
                "접속 횟수": lk.access_count,
            }
            for lk in links
        ],
        hide_index=True,
        width="stretch",
    )
    soon = [lk for lk in links if statuses[lk.share_id] == sharing.STATUS_SOON]
    if soon:
        st.warning(f"{sharing.EXPIRING_SOON_DAYS}일 이내 만료 예정 링크 {len(soon)}건")

    revocable = [lk for lk in links if statuses[lk.share_id] in (sharing.STATUS_ACTIVE, sharing.STATUS_SOON)]
    if revocable:
        with st.form("share_revoke"):
            target = st.selectbox(
                "회수할 링크", revocable,
                format_func=lambda lk: f"#{lk.share_id} {pool_names.get(lk.pool_id, '')} → {lk.recipient_email}",
            )
            confirm = st.checkbox("즉시 회수합니다. 수신자는 다음 요청부터 열람할 수 없습니다.")
            if st.form_submit_button("회수"):
                if confirm:
                    sharing.revoke(target.share_id, user.user_id)
                    st.rerun()
                else:
                    st.warning("회수 확인란을 선택하세요.")

    # ---------------- 접속 이력 (F-09-15)
    st.divider()
    st.subheader("접속 이력")
    chosen = st.selectbox(
        "링크 선택", links,
        format_func=lambda lk: f"#{lk.share_id} {pool_names.get(lk.pool_id, '')} → {lk.recipient_email}",
        key="share_history_pick",
    )
    history = sharing.access_history(chosen.share_id)
    if history:
        st.dataframe(
            [{"시각": h.occurred_at.strftime("%Y-%m-%d %H:%M:%S"), "사용자": h.user_id or "-",
              "행위": h.action, "상세": h.detail or "-"} for h in history],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("기록이 없습니다.")

st.caption("사외(자문 법무법인 등) 공유 허용 범위는 법무·개인정보 결정 대기 사항입니다. (PRD §14-12)")
