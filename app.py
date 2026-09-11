"""독립이사 후보자 POOL — 진입점.

역할
1. DB 부트스트랩
2. 로그인 게이트 (미인증 상태에서는 어떤 페이지도 실행되지 않는다)
3. 역할별 네비게이션 구성 (PRD F-09-11)

st.navigation 을 쓰는 이유: pages/ 자동 네비게이션은 역할과 무관하게 모든 페이지를
사이드바에 노출하고 URL 접근도 허용한다. 네비게이션을 직접 구성해 접근 가능한
페이지만 라우팅에 올리고, 각 페이지는 다시 core.guard.require() 로 재검증한다.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core import audit, constants as C, settings, sharing, state  # noqa: E402
from core.auth import accessible_pages, get_provider, is_session_expired, refresh_user  # noqa: E402
from core.ui import style as ui_style  # noqa: E402
from data import repository  # noqa: E402
from data.session import init_db  # noqa: E402

st.set_page_config(
    page_title="독립이사 후보자 POOL",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui_style.inject()


@st.cache_resource
def bootstrap() -> dict:
    """테이블 생성 및 기동 점검. 커넥션 캐시 성격이라 cache_resource 를 쓴다.

    배포 환경(Streamlit Cloud 등)은 매번 빈 DB 로 시작하고 `python -m data.seed` 를
    수동 실행할 셸 접근이 없으므로, 더미 모드에서 데이터가 비어 있으면 자동으로
    한 번 시딩한다(PERSON_COUNT=200 기본값 기준 다소 시간이 걸릴 수 있다).
    """
    init_db()
    if os.getenv("DATA_MODE", "dummy").lower() != "live" and repository.person_count() == 0:
        from data import seed

        seed.run()
    return {"ok": True}


bootstrap()


# ------------------------------------------------------------------ 로그인 화면

def render_login() -> None:
    # 단순·명확이 목표다(3단계 §C S-00) — 좁은 중앙 열 하나에 로그인과 안내만 둔다.
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown('<div class="pool-system-caption">⚖️ 이사회 사무국 전용 · 대외비</div>', unsafe_allow_html=True)
        st.title("독립이사 후보자 POOL")

        provider = get_provider()
        if provider.name == "mock":
            st.warning(
                "**개발 모드(모의 로그인)** 입니다. 운영 배포 전 SSO(OIDC) 연동으로 교체해야 합니다. "
                "(PRD F-09-10)",
                icon="⚠️",
            )

        try:
            candidates = provider.list_selectable_users()
        except Exception:
            candidates = []

        if not candidates:
            st.error("로그인 가능한 계정이 없습니다.")
            st.code("python -m data.seed", language="bash")
            st.caption("위 명령으로 더미데이터와 계정을 생성한 뒤 새로고침하세요.")
            return

        with st.form("login"):
            labels = {f"{u.display_name} · {u.role} ({u.email})": u.email for u in candidates}
            picked = st.selectbox("계정 선택", list(labels.keys()))
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)

        if submitted:
            user = provider.authenticate(labels[picked])
            if user is None:
                st.error("로그인할 수 없는 계정입니다. 접근 권한이 만료되었을 수 있습니다.")
                return
            state.clear_user_scoped()
            state.put(state.K_USER, user)
            state.touch()
            audit.log_access(user.user_id, C.ACT_LOGIN, page="login")
            st.rerun()

        with st.expander("이 시스템에 대하여"):
            st.markdown(
                """
                - 공개된 신뢰성 높은 자료(DART·기관 공식 정보·언론)만 사용하며, 모든 항목에 출처를 표기합니다.
                - 화면의 정보는 **참고자료**이며, 최종 적격성은 법무 검토로 확정됩니다.
                - 모든 조회·출력·공유 행위는 감사로그에 기록됩니다.
                """
            )


# ------------------------------------------------------------------ 사이드바

def render_sidebar(user) -> None:
    with st.sidebar:
        st.markdown(f"**{user.display_name}**")
        st.caption(f"{user.role} · {user.email}")
        if user.expires_at:
            st.caption(f"접근 만료: {user.expires_at.isoformat()}")
        st.divider()
        if st.button("로그아웃", use_container_width=True):
            audit.log_access(user.user_id, C.ACT_LOGOUT, page="sidebar")
            state.clear_user_scoped()
            st.rerun()
        st.caption("대외비 — 무단 반출 금지")


# ------------------------------------------------------------------ 라우팅

PAGE_SPECS = [
    ("dashboard", "pages/0_대시보드.py", "대시보드", ":material/dashboard:"),
    ("search", "pages/1_후보_검색.py", "후보 검색", ":material/search:"),
    ("detail", "pages/2_후보_상세.py", "후보 상세", ":material/person:"),
    ("compare", "pages/3_후보_비교.py", "후보 비교", ":material/compare:"),
    ("pool", "pages/4_POOL_관리.py", "POOL 관리", ":material/folder:"),
    ("review", "pages/5_검수.py", "검수", ":material/fact_check:"),
    ("report", "pages/6_리포트.py", "리포트", ":material/description:"),
    ("share", "pages/8_공유_관리.py", "공유 관리", ":material/share:"),
    ("admin", "pages/7_관리자.py", "관리자", ":material/settings:"),
]


def _capture_share_token() -> None:
    """?share=<토큰> 은 보관만 하고 주소창에서 즉시 지운다. 검증은 로그인 후에만 한다 (F-09-14)."""
    token = st.query_params.get("share")
    if token:
        state.put(state.K_PENDING_SHARE, token)
        del st.query_params["share"]


def _consume_share_token(user) -> bool:
    """로그인한 사용자의 이메일이 링크 수신자와 같을 때만 통과. 실패 사유는 그대로 알린다."""
    token = state.get(state.K_PENDING_SHARE)
    if not token:
        return False
    st.session_state.pop(state.K_PENDING_SHARE, None)
    try:
        _, pool_id = sharing.verify_token(token, user.user_id, user.email)
    except sharing.ShareDenied as exc:
        st.error(f"공유 링크로 접근할 수 없습니다 — {exc}")
        return False
    state.put(state.K_SELECTED_POOL, pool_id)
    st.success("공유받은 POOL 을 열었습니다. 읽기 전용이며 다운로드할 수 없습니다.")
    return True


def main() -> None:
    _capture_share_token()
    user = state.get(state.K_USER)

    if user is None:
        if state.get(state.K_PENDING_SHARE):
            st.info("공유 링크로 접속했습니다. 링크만으로는 열람할 수 없으며, 로그인 후 수신자 확인을 거칩니다.")
        render_login()
        return

    idle = settings.get_int(C.SET_SESSION_IDLE_MINUTES, default=30)
    if is_session_expired(state.get(state.K_LAST_ACTIVE), idle):
        audit.log_access(user.user_id, C.ACT_LOGOUT, page="app", detail="idle timeout")
        state.clear_user_scoped()
        st.warning(f"{idle}분 이상 사용하지 않아 자동 로그아웃되었습니다.")
        render_login()
        return

    # 매 요청 계정 재검증 — 비활성화·만료·역할 변경 즉시 반영 (F-09-11·12)
    fresh = refresh_user(user.user_id)
    if fresh is None:
        audit.log_access(user.user_id, C.ACT_LOGOUT, page="app", detail="account inactive or expired")
        state.clear_user_scoped()
        st.warning("계정이 비활성화되었거나 접근 기간이 만료되었습니다.")
        render_login()
        return
    if fresh != user:
        state.put(state.K_USER, fresh)
        user = fresh

    opened_pool = _consume_share_token(user)

    allowed = set(accessible_pages(user.role))
    default_key = "pool" if opened_pool and "pool" in allowed else "dashboard"
    pages = [
        st.Page(path, title=title, icon=icon, default=(key == default_key))
        for key, path, title, icon in PAGE_SPECS
        if key in allowed
    ]
    if not pages:
        st.error("접근 가능한 화면이 없습니다. 관리자에게 문의하세요.")
        return

    render_sidebar(user)

    if repository.person_count() == 0:
        st.info("후보자 데이터가 없습니다. `python -m data.seed` 로 더미데이터를 생성하세요.")

    if os.getenv("DATA_MODE", "dummy").lower() != "live":
        st.caption("🧪 더미 모드 — 표시되는 인물은 모두 합성 데이터이며 실존 인물이 아닙니다.")

    st.navigation(pages).run()


main()
