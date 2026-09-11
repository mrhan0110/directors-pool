"""테스트 공용 도구.

화면 가드는 매 요청 DB 에서 계정을 다시 읽으므로(auth.refresh_user), 테스트도 역할에 맞는
실제 시드 계정으로 로그인해야 한다.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core.auth import CurrentUser, _to_current
from data.models import AppUser
from data.session import session_scope


def user_for(role: str) -> CurrentUser:
    """해당 역할의 활성·미만료 시드 계정."""
    with session_scope() as s:
        for u in s.execute(select(AppUser).where(AppUser.role == role, AppUser.is_active.is_(True))
                           .order_by(AppUser.user_id)).scalars():
            if u.expires_at is None or u.expires_at >= date.today():
                return _to_current(u)
    raise LookupError(f"시드에 {role} 계정이 없습니다")
