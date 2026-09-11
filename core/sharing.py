"""공유 링크 (PRD F-09-12, F-09-14 ~ F-09-16).

- 링크는 POOL ID + 만료일시 + 수신자 이메일에 바인딩된 토큰이다. DB 에는 토큰의 sha256 해시만 저장한다.
- 토큰만으로는 열람할 수 없다. 로그인한 사용자의 이메일이 수신자와 일치해야 한다.
- 회수·만료는 다음 요청부터 즉시 반영된다 — 접근 범위를 매 요청 DB 에서 다시 계산하기 때문이다(core/access.py).
- 발급·접속·회수·거부는 모두 AccessLog 에 남는다 (F-09-15, F-09-22).
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select

from core import constants as C
from core import settings
from core.audit import log_access
from data.models import AccessLog, AppUser, Pool, ShareLink
from data.session import session_scope

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EXPIRING_SOON_DAYS = 7
SCOPE_READ_ONLY = "read_only"

STATUS_ACTIVE = "유효"
STATUS_SOON = "만료 임박"
STATUS_EXPIRED = "만료"
STATUS_REVOKED = "회수"


class ShareDenied(PermissionError):
    """공유 링크로 접근할 수 없음. 메시지는 사용자에게 그대로 보여준다."""


@dataclass(frozen=True)
class IssuedLink:
    share_id: int
    token: str      # 원문 토큰은 발급 직후 한 번만 보여주고 저장하지 않는다
    url: str
    expires_at: datetime


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_naive(dt: datetime | None = None) -> datetime:
    """DB(SQLite/PostgreSQL timestamp without tz)와 비교하기 위한 UTC naive 시각."""
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def default_expiry(today: date | None = None) -> date:
    return (today or date.today()) + timedelta(days=settings.get_int(C.SET_SHARE_LINK_DEFAULT_DAYS))


def max_expiry(today: date | None = None) -> date:
    return (today or date.today()) + timedelta(days=settings.get_int(C.SET_SHARE_LINK_MAX_DAYS))


def build_url(token: str) -> str:
    base = os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")
    return f"{base}/?share={token}"


def issue_link(
    pool_id: int,
    issued_by: int | None,
    recipient_email: str,
    purpose: str,
    expires_on: date | None,
    scope: str = SCOPE_READ_ONLY,
    today: date | None = None,
) -> IssuedLink:
    """발급 시 수신자·목적·범위·만료일은 모두 필수다 (F-09-15)."""
    today = today or date.today()
    email = (recipient_email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("수신자 이메일 형식이 올바르지 않습니다.")
    if not (purpose or "").strip():
        raise ValueError("공유 목적을 입력하세요.")
    if scope != SCOPE_READ_ONLY:
        raise ValueError("공유 범위는 POOL 단위 읽기 전용만 허용됩니다.")
    if expires_on is None:
        raise ValueError("만료일을 지정하세요.")
    if expires_on <= today:
        raise ValueError("만료일은 오늘 이후여야 합니다.")
    if expires_on > max_expiry(today):
        raise ValueError(f"만료일은 최대 {settings.get_int(C.SET_SHARE_LINK_MAX_DAYS)}일 이내로 지정해야 합니다.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.combine(expires_on, time(23, 59, 59))
    with session_scope() as s:
        if s.get(Pool, pool_id) is None:
            raise LookupError(f"POOL 이 없습니다: {pool_id}")
        recipient = s.execute(
            select(AppUser).where(func.lower(AppUser.email) == email)
        ).scalar_one_or_none()
        if recipient is None or not recipient.is_active:
            raise ValueError(
                "해당 이메일로 등록된 활성 계정이 없습니다. 관리자에게 외부뷰어 계정 발급을 먼저 요청하세요. (PRD F-09-10)"
            )
        link = ShareLink(
            pool_id=pool_id,
            issued_by=issued_by,
            recipient_email=email,
            purpose=purpose.strip(),
            scope=scope,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        s.add(link)
        s.flush()
        share_id = link.share_id
    log_access(issued_by, C.ACT_SHARE_ISSUE, page="share", share_id=share_id,
               detail=f"pool={pool_id}, to={email}, until={expires_on.isoformat()}")
    return IssuedLink(share_id, token, build_url(token), expires_at)


def revoke(share_id: int, user_id: int | None) -> None:
    """즉시 회수. 이미 회수된 링크는 그대로 둔다."""
    with session_scope() as s:
        link = s.get(ShareLink, share_id)
        if link is None:
            raise LookupError(f"공유 링크가 없습니다: {share_id}")
        if link.revoked_at is not None:
            return
        link.revoked_at = _utc_naive()
    log_access(user_id, C.ACT_SHARE_REVOKE, page="share", share_id=share_id)


def status_of(link: ShareLink, now: datetime | None = None) -> str:
    now = _utc_naive(now)
    if link.revoked_at is not None:
        return STATUS_REVOKED
    expires = _utc_naive(link.expires_at)
    if expires < now:
        return STATUS_EXPIRED
    if expires - now <= timedelta(days=EXPIRING_SOON_DAYS):
        return STATUS_SOON
    return STATUS_ACTIVE


def verify_token(token: str, user_id: int | None, email: str, now: datetime | None = None) -> tuple[int, int]:
    """로그인한 사용자가 링크로 들어왔을 때 검증한다. (share_id, pool_id) 를 반환한다."""
    now = _utc_naive(now)
    with session_scope() as s:
        link = s.execute(
            select(ShareLink).where(ShareLink.token_hash == hash_token(token or ""))
        ).scalar_one_or_none()
        reason = None
        if link is None:
            reason = "유효하지 않은 공유 링크입니다."
        elif link.revoked_at is not None:
            reason = "회수된 공유 링크입니다."
        elif _utc_naive(link.expires_at) < now:
            reason = "만료된 공유 링크입니다."
        elif link.recipient_email.lower() != (email or "").lower():
            reason = "이 링크는 다른 수신자에게 발급되었습니다."
        share_id = link.share_id if link else None
        if reason is None:
            link.access_count += 1
            pool_id = link.pool_id
    if reason:
        log_access(user_id, C.ACT_DENIED, page="share_link", share_id=share_id, detail=reason)
        raise ShareDenied(reason)
    log_access(user_id, C.ACT_SHARE_ACCESS, page="share_link", share_id=share_id, detail=f"pool={pool_id}")
    return share_id, pool_id


def active_links_for(email: str, now: datetime | None = None) -> list[ShareLink]:
    """본인 이메일로 발급된 유효 링크. 외부뷰어의 접근 범위는 오직 이것으로 정한다."""
    now = _utc_naive(now)
    with session_scope() as s:
        return list(
            s.execute(
                select(ShareLink).where(
                    func.lower(ShareLink.recipient_email) == (email or "").lower(),
                    ShareLink.revoked_at.is_(None),
                    ShareLink.expires_at >= now,
                )
            ).scalars()
        )


def list_links(pool_id: int | None = None) -> list[ShareLink]:
    with session_scope() as s:
        stmt = select(ShareLink).order_by(ShareLink.issued_at.desc(), ShareLink.share_id.desc())
        if pool_id is not None:
            stmt = stmt.where(ShareLink.pool_id == pool_id)
        return list(s.execute(stmt).scalars())


def access_history(share_id: int, limit: int = 200) -> list[AccessLog]:
    with session_scope() as s:
        return list(
            s.execute(
                select(AccessLog)
                .where(AccessLog.share_id == share_id)
                .order_by(AccessLog.occurred_at.desc(), AccessLog.log_id.desc())
                .limit(limit)
            ).scalars()
        )
