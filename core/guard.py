"""화면 가드 (PRD F-09-11, F-09-13).

모든 페이지는 최상단에서 require(page_key) 를 호출한다.
메뉴에서 숨기는 것만으로는 불충분하므로 페이지 자체에서 다시 검증한다.
"""

from __future__ import annotations

import streamlit as st

from core import audit, constants as C, settings, state
from core.auth import CurrentUser, can_access, can_download, is_session_expired


def current_user() -> CurrentUser | None:
    return state.get(state.K_USER)


def require(page_key: str) -> CurrentUser:
    """인증·권한·세션유효성을 모두 통과해야 아래 코드가 실행된다.

    통과하지 못하면 st.stop() 으로 렌더링을 중단한다.
    """
    user = current_user()

    if user is None:
        st.error("로그인이 필요합니다.")
        st.caption("좌측 상단 홈 화면에서 로그인하세요.")
        audit.log_denied(None, page_key, None)
        st.stop()

    # 유휴 세션 만료 (PRD F-09-13)
    idle = settings.get_int(C.SET_SESSION_IDLE_MINUTES, default=30)
    if is_session_expired(state.get(state.K_LAST_ACTIVE), idle):
        audit.log_access(user.user_id, C.ACT_LOGOUT, page=page_key, detail="idle timeout")
        state.clear_user_scoped()
        st.warning(f"{idle}분 이상 사용하지 않아 자동 로그아웃되었습니다. 다시 로그인하세요.")
        st.stop()

    if not can_access(user.role, page_key):
        st.error("이 페이지에 접근할 권한이 없습니다.")
        st.caption(f"현재 역할: {user.role}")
        audit.log_denied(user.user_id, page_key, user.role)
        st.stop()

    state.touch()
    audit.log_access(user.user_id, C.ACT_VIEW, page=page_key)
    return user


def require_download(user: CurrentUser) -> bool:
    """다운로드 가능 여부. 외부뷰어는 불가 (PRD F-09-12)."""
    return can_download(user.role)


def confidential_notice() -> None:
    st.caption(
        "대외비 · 본 자료는 공개정보 기반 참고자료이며, 최종 판단은 담당자·법무 검토로 확정됩니다."
    )


def stage_notice(text: str) -> None:
    """1단계 뼈대에서 아직 구현되지 않은 영역 표시."""
    st.info(f"🚧 {text}", icon="🚧")
