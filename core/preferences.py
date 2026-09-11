"""사용자별 최근 선택값 (PRD F-01-8 '사용자별 최근 선택값을 기억하여 다음 검색 시 기본 적용').

세션이 끝나도 유지되어야 하므로 st.session_state 가 아니라 DB(UserPreference)에 둔다.
"""

from __future__ import annotations

from data.models import UserPreference
from data.session import session_scope

KEY_RESULT_LIMIT = "search.limit_code"


def get_pref(user_id: int, key: str, default: str | None = None) -> str | None:
    with session_scope() as s:
        row = s.get(UserPreference, (user_id, key))
        return row.value if row else default


def set_pref(user_id: int, key: str, value: str) -> None:
    with session_scope() as s:
        row = s.get(UserPreference, (user_id, key))
        if row is None:
            s.add(UserPreference(user_id=user_id, key=key, value=value))
        elif row.value != value:
            row.value = value
