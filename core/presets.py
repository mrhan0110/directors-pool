"""검색 프리셋 (PRD F-01-5). 조회 인원 수도 함께 저장한다 (F-01-8).

프리셋은 사용자 소유다. 다른 사용자의 프리셋을 읽거나 지울 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from data.models import SearchPreset
from data.session import session_scope

MAX_NAME = 200


@dataclass(frozen=True)
class Preset:
    id: int
    name: str
    filters: dict
    limit_code: str | None


def _to(row: SearchPreset) -> Preset:
    return Preset(id=row.id, name=row.name, filters=dict(row.filters or {}), limit_code=row.limit_code)


def list_presets(user_id: int) -> list[Preset]:
    with session_scope() as s:
        rows = s.execute(
            select(SearchPreset).where(SearchPreset.user_id == user_id).order_by(SearchPreset.name)
        ).scalars()
        return [_to(r) for r in rows]


def get_preset(user_id: int, preset_id: int) -> Preset | None:
    with session_scope() as s:
        row = s.get(SearchPreset, preset_id)
        if row is None or row.user_id != user_id:
            return None
        return _to(row)


def save_preset(user_id: int, name: str, filters: dict, limit_code: str | None) -> int:
    """같은 이름이 있으면 덮어쓴다."""
    name = (name or "").strip()
    if not name:
        raise ValueError("프리셋 이름을 입력하세요.")
    if len(name) > MAX_NAME:
        raise ValueError(f"프리셋 이름은 {MAX_NAME}자 이내로 입력하세요.")
    with session_scope() as s:
        row = s.execute(
            select(SearchPreset).where(SearchPreset.user_id == user_id, SearchPreset.name == name)
        ).scalar_one_or_none()
        if row is None:
            row = SearchPreset(user_id=user_id, name=name)
            s.add(row)
        row.filters = dict(filters)
        row.limit_code = limit_code
        s.flush()
        return row.id


def delete_preset(user_id: int, preset_id: int) -> bool:
    with session_scope() as s:
        row = s.get(SearchPreset, preset_id)
        if row is None or row.user_id != user_id:
            return False
        s.delete(row)
        return True
