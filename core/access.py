"""데이터 접근 범위 (PRD F-09-12, 부록 C #3).

외부뷰어는 본인 이메일로 발급된 유효한 공유 링크의 POOL 과 그 구성원만 볼 수 있다.
범위는 매 요청 DB 에서 다시 계산한다 — 세션에 저장된 값을 신뢰하지 않으므로,
링크를 회수하거나 만료되면 다음 요청부터 곧바로 차단된다.
내부 역할(담당자·사무국장·법무·관리자)은 None(제한 없음)을 반환한다.
"""

from __future__ import annotations

from core import pools, sharing
from core.auth import CurrentUser


def allowed_pool_ids(user: CurrentUser | None) -> list[int] | None:
    if user is None:
        return []
    if not user.is_viewer:
        return None
    return sorted({link.pool_id for link in sharing.active_links_for(user.email)})


def allowed_person_ids(user: CurrentUser | None) -> set[int] | None:
    pool_ids = allowed_pool_ids(user)
    if pool_ids is None:
        return None
    return pools.member_ids(pool_ids)


def can_view_person(user: CurrentUser | None, person_id: int) -> bool:
    ids = allowed_person_ids(user)
    return ids is None or person_id in ids


def can_view_pool(user: CurrentUser | None, pool_id: int) -> bool:
    ids = allowed_pool_ids(user)
    return ids is None or pool_id in ids


def filter_person_options(user: CurrentUser | None, options: list[tuple[int, str]]) -> list[tuple[int, str]]:
    ids = allowed_person_ids(user)
    return options if ids is None else [o for o in options if o[0] in ids]
