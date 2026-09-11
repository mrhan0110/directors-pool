"""st.session_state 접근 유틸 (PRD F-09-4).

세션 키를 문자열로 흩뿌리지 않기 위한 단일 통로.
검색 조건은 페이지를 이동했다 돌아와도 유지되어야 한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

# 세션 키
K_USER = "auth.user"
K_LAST_ACTIVE = "auth.last_active"
K_FILTERS = "search.filters"
K_RESULT_LIMIT = "search.result_limit_code"
K_LAST_SEARCH = "search.last_result"
K_PAGE = "search.page"
K_SIGNATURE = "search.signature"      # 조건이 바뀌면 1페이지로 돌아가기 위한 비교값
K_LOGGED = "search.logged_signature"  # 같은 검색을 재실행마다 중복 로깅하지 않기 위함
K_EXPORT = "export.xlsx"              # 생성된 내보내기 파일(개인정보 포함 — 로그아웃 시 삭제)
K_EXPORT_SIG = "export.signature"
K_REPORT = "report.pdf"               # 생성된 PDF(개인정보 포함 — 로그아웃 시 삭제)
K_REPORT_SIG = "report.signature"
K_SELECTED_PERSON = "nav.selected_person_id"
K_COMPARE_BASKET = "nav.compare_basket"
K_TOAST = "ui.toast"

DEFAULT_FILTERS: dict[str, Any] = {
    "gender": None,
    "age_bands": [],
    "job_scope": "BOTH",
    "job_l1": [],
    "job_l2": [],
    "role_levels": [],
    "expertise_l1": [],
    "expertise_l2": [],
    "industries": [],
    "nationalities": [],
    "concurrent": None,
    "term_remain": None,
    "screening": None,
    "reputation": None,
    "regions": [],
    "freshness": None,
    "sort": "FIT",
}


def get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def put(key: str, value: Any) -> None:
    st.session_state[key] = value


def touch() -> None:
    """유휴 타이머 갱신 (PRD F-09-13)."""
    st.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)


def filters() -> dict[str, Any]:
    if K_FILTERS not in st.session_state:
        st.session_state[K_FILTERS] = dict(DEFAULT_FILTERS)
    return st.session_state[K_FILTERS]


def set_filter(name: str, value: Any) -> None:
    f = filters()
    f[name] = value
    st.session_state[K_FILTERS] = f


def reset_filters() -> None:
    st.session_state[K_FILTERS] = dict(DEFAULT_FILTERS)


def clear_dependent(parent: str) -> None:
    """상위 선택이 바뀌면 하위 선택을 초기화한다 (PRD F-01-2, F-09-3)."""
    mapping = {"job_l1": "job_l2", "expertise_l1": "expertise_l2"}
    child = mapping.get(parent)
    if child:
        set_filter(child, [])


def compare_basket() -> list[int]:
    if K_COMPARE_BASKET not in st.session_state:
        st.session_state[K_COMPARE_BASKET] = []
    return st.session_state[K_COMPARE_BASKET]


def clear_user_scoped() -> None:
    """로그아웃 시 사용자 종속 상태를 전부 비운다.

    역할 전환 후 이전 역할의 데이터가 남으면 권한 경계가 무너진다. (PRD §11)
    """
    for key in (
        K_USER,
        K_LAST_ACTIVE,
        K_FILTERS,
        K_RESULT_LIMIT,
        K_LAST_SEARCH,
        K_PAGE,
        K_SIGNATURE,
        K_LOGGED,
        K_EXPORT,
        K_EXPORT_SIG,
        K_REPORT,
        K_REPORT_SIG,
        K_SELECTED_PERSON,
        K_COMPARE_BASKET,
    ):
        st.session_state.pop(key, None)
