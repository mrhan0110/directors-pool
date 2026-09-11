"""화면 가드 (PRD F-09-11, F-09-12, F-09-13, F-09-17).

모든 페이지는 최상단에서 require(page_key) 를 호출한다.
메뉴에서 숨기는 것만으로는 불충분하므로 페이지 자체에서 다시 검증한다.
세션에 저장된 사용자 정보(역할·만료일)는 믿지 않고 매 요청 DB 에서 다시 읽는다.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import audit, constants as C, settings, state
from core.auth import CurrentUser, can_access, can_download, is_session_expired, refresh_user
from core.ui.components import confidential_banner


def current_user() -> CurrentUser | None:
    return state.get(state.K_USER)


def require(page_key: str) -> CurrentUser:
    """인증·계정 유효성·권한·세션 유휴를 모두 통과해야 아래 코드가 실행된다.

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

    # 계정 재검증: 비활성화·접근 만료·역할 변경을 즉시 반영 (F-09-11·12)
    fresh = refresh_user(user.user_id)
    if fresh is None:
        audit.log_access(user.user_id, C.ACT_LOGOUT, page=page_key, detail="account inactive or expired")
        state.clear_user_scoped()
        st.error("계정이 비활성화되었거나 접근 기간이 만료되었습니다. 관리자에게 문의하세요.")
        st.stop()
    if fresh != user:
        state.put(state.K_USER, fresh)
        user = fresh

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
    """대외비 고지 + 열람자·일시 표시 (F-09-17). 화면 캡처가 반출돼도 출처를 추적할 수 있게 한다."""
    user = current_user()
    stamp = f" · 열람자 {user.email} · {datetime.now():%Y-%m-%d %H:%M}" if user else ""
    confidential_banner(
        "대외비 · 본 자료는 공개정보 기반 참고자료이며, 최종 판단은 담당자·법무 검토로 확정됩니다." + stamp
    )


def stage_notice(text: str) -> None:
    """아직 구현되지 않은 영역 표시."""
    st.info(f"🚧 {text}", icon="🚧")
