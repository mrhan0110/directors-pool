"""S-09 공유 관리 (PRD F-09-14~18). 구현은 2단계 J 항목."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from core import constants as C, settings
from core.guard import confidential_notice, require, stage_notice
from data.models import ShareLink
from data.repository import list_pools
from data.session import session_scope

user = require("share")

st.title("공유 관리")
confidential_notice()

default_days = settings.get_int(C.SET_SHARE_LINK_DEFAULT_DAYS)

st.info(
    f"""
    공유 링크 정책
    - 링크는 **POOL + 수신자 이메일 + 만료일시**에 바인딩되며, 토큰만으로는 열람할 수 없습니다(로그인 필수).
    - 기본 만료 기간은 **{default_days}일** 이며 관리자 화면에서 조정합니다.
    - 발급·접속·회수 이력은 모두 감사로그에 남습니다.
    - 회수하면 즉시 접근이 차단됩니다.
    """,
    icon="🔐",
)

pools = list_pools()
if pools:
    st.selectbox("공유할 POOL", pools, format_func=lambda p: p.name, disabled=True)
st.text_input("수신자 이메일", disabled=True, placeholder="2단계에서 활성화")
st.text_area("공유 목적", disabled=True, placeholder="2단계에서 활성화")
st.button("공유 링크 발급 (2단계)", disabled=True)

st.divider()
st.subheader("발급 현황")
with session_scope() as s:
    links = list(s.execute(select(ShareLink).order_by(ShareLink.issued_at.desc())).scalars())

if links:
    st.dataframe(
        [
            {
                "POOL": lk.pool_id,
                "수신자": lk.recipient_email,
                "발급": lk.issued_at.date().isoformat(),
                "만료": lk.expires_at.date().isoformat(),
                "회수": lk.revoked_at.date().isoformat() if lk.revoked_at else "-",
                "접속 횟수": lk.access_count,
            }
            for lk in links
        ],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.caption("발급된 공유 링크가 없습니다.")

stage_notice(
    "공유 링크 발급·회수·접속 이력은 2단계(J)에서 구현합니다. "
    "사외 공유 허용 범위는 법무·개인정보 결정 대기 사항입니다. (PRD §14-12)"
)
