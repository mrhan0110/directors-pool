"""인증·권한의 순수 로직 (PRD F-09-10 ~ F-09-13).

Streamlit 에 의존하지 않는다. 화면 가드는 core/guard.py 가 담당한다.
1단계는 mock 프로바이더만 구현하되, 3.5단계에 OIDC 로 교체할 수 있도록
AuthProvider 인터페이스를 먼저 고정해 둔다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select

from core import constants as C
from data.models import AppUser
from data.session import session_scope


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    email: str
    display_name: str
    role: str
    org_affiliation: str | None = None
    expires_at: date | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == C.ROLE_ADMIN

    @property
    def is_viewer(self) -> bool:
        return self.role == C.ROLE_VIEWER


class AuthProvider(Protocol):
    name: str

    def list_selectable_users(self) -> list[CurrentUser]:
        """mock 전용. 실제 IdP 연동 시에는 빈 목록을 반환한다."""
        ...

    def authenticate(self, identifier: str) -> CurrentUser | None:
        ...


class MockAuthProvider:
    """개발용 모의 로그인. 계정 목록에서 골라 로그인한다.

    운영 배포 전 반드시 OIDC 로 교체한다. AUTH_PROVIDER=mock 인 동안
    화면 상단에 개발 모드 경고를 노출한다 (app.py).
    """

    name = "mock"

    def list_selectable_users(self) -> list[CurrentUser]:
        with session_scope() as s:
            rows = s.execute(
                select(AppUser).where(AppUser.is_active.is_(True)).order_by(AppUser.user_id)
            ).scalars()
            return [_to_current(u) for u in rows]

    def authenticate(self, identifier: str) -> CurrentUser | None:
        with session_scope() as s:
            user = s.execute(select(AppUser).where(AppUser.email == identifier)).scalar_one_or_none()
            if user is None or not user.is_active:
                return None
            if user.expires_at is not None and user.expires_at < date.today():
                # 외부뷰어 접근 만료 (PRD F-09-12)
                return None
            user.last_login_at = datetime.now(timezone.utc)
            return _to_current(user)


class OIDCAuthProvider:
    """3.5단계 구현 예정 (PRD F-09-10). 인터페이스만 고정해 둔다."""

    name = "oidc"

    def list_selectable_users(self) -> list[CurrentUser]:
        return []

    def authenticate(self, identifier: str) -> CurrentUser | None:  # pragma: no cover
        raise NotImplementedError(
            "OIDC 연동은 3.5단계 작업입니다. AUTH_PROVIDER=mock 으로 실행하세요."
        )


def _to_current(user: AppUser) -> CurrentUser:
    return CurrentUser(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        org_affiliation=user.org_affiliation,
        expires_at=user.expires_at,
    )


def get_provider() -> AuthProvider:
    name = os.getenv("AUTH_PROVIDER", "mock").lower()
    return OIDCAuthProvider() if name == "oidc" else MockAuthProvider()


# ------------------------------------------------------------------ 권한 매트릭스
# 페이지 키 -> 접근 가능 역할. 외부뷰어는 지정 POOL 열람과 후보 상세만 허용한다 (PRD F-09-12).
PAGE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "dashboard": C.ALL_ROLES,
    "search": (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN),
    "detail": C.ALL_ROLES,
    "compare": (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN),
    "pool": C.ALL_ROLES,
    "review": (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN),
    "report": (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN),
    "share": (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_ADMIN),
    "admin": (C.ROLE_ADMIN,),
}

# 다운로드는 외부뷰어에게 허용하지 않는다 (PRD F-09-12)
DOWNLOAD_ALLOWED_ROLES = (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN)

# POOL 편집은 담당자·사무국장(·관리자). 법무는 조회와 검증 결과 입력만 한다 (PRD §3.1)
POOL_EDIT_ROLES = (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_ADMIN)


def can_edit_pool(role: str | None) -> bool:
    return role in POOL_EDIT_ROLES


# 검수·고려사항 수기 확인 입력: 외부뷰어를 제외한 내부 역할
REVIEW_ROLES = (C.ROLE_STAFF, C.ROLE_HEAD, C.ROLE_LEGAL, C.ROLE_ADMIN)
# 결격·이해상충 수기 판정: 법무(·관리자) (PRD §3.1 '검증 결과 입력')
SCREENING_OVERRIDE_ROLES = (C.ROLE_LEGAL, C.ROLE_ADMIN)


def can_review(role: str | None) -> bool:
    return role in REVIEW_ROLES


def can_override_screening(role: str | None) -> bool:
    return role in SCREENING_OVERRIDE_ROLES


def can_access(role: str | None, page_key: str) -> bool:
    if role is None:
        return False
    allowed = PAGE_PERMISSIONS.get(page_key)
    if allowed is None:
        # 등록되지 않은 페이지는 기본 차단 (fail-closed)
        return False
    return role in allowed


def can_download(role: str | None) -> bool:
    return role in DOWNLOAD_ALLOWED_ROLES


def accessible_pages(role: str | None) -> list[str]:
    return [key for key in PAGE_PERMISSIONS if can_access(role, key)]


def is_session_expired(last_active: datetime | None, idle_minutes: int, now: datetime | None = None) -> bool:
    """세션 유휴 자동 로그아웃 판정 (PRD F-09-13)."""
    if last_active is None:
        return True
    now = now or datetime.now(timezone.utc)
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    return (now - last_active) > timedelta(minutes=idle_minutes)
