"""운영 파라미터 접근자.

법령 연동 임계값을 코드에서 직접 쓰지 않도록 하는 유일한 통로다.
호출부는 반드시 get_int(SET_CONCURRENT_LIMIT) 형태로 읽는다. (불변규칙 4)
"""

from __future__ import annotations

from sqlalchemy import select

from core import constants as C
from data.models import AppSetting
from data.session import session_scope

# 시드 기본값. PRD §14 미결 사항으로 남은 값은 '결정 대기' 임을 description 에 명시한다.
DEFAULTS: list[dict] = [
    {
        "key": C.SET_RESULT_LIMIT_DEFAULT,
        "value": "30",
        "value_type": "int",
        "description": "최대 조회 인원 수 기본값 (PRD F-01-8)",
    },
    {
        "key": C.SET_RESULT_LIMIT_SYSTEM_MAX,
        "value": "500",
        "value_type": "int",
        "description": "'전체' 선택 시에도 넘을 수 없는 시스템 상한 (PRD F-01-8, §14-16 결정 대기)",
    },
    {
        "key": C.SET_RESULT_LIMIT_VIEWER_MAX,
        "value": "50",
        "value_type": "int",
        "description": "외부뷰어 역할의 조회 상한 (PRD F-01-8)",
    },
    {
        "key": C.SET_PAGE_SIZE,
        "value": "50",
        "value_type": "int",
        "description": "목록 1페이지 표시 건수. 조회 인원 수(N)와 별개 개념 (PRD F-02-5)",
    },
    {
        "key": C.SET_CAREER_LOOKBACK_YEARS,
        "value": "10",
        "value_type": "int",
        "description": "과거 경력 표출 기간(년) (PRD F-03 (3))",
    },
    {
        "key": C.SET_TERM_ALERT_MONTHS,
        "value": "6",
        "value_type": "int",
        "description": "잔여 임기 강조 기준(개월) (PRD F-03-1)",
    },
    {
        "key": C.SET_CONCURRENT_LIMIT,
        "value": "2",
        "value_type": "int",
        "description": "타사 상장사 겸직 허용 수. 초과 시 오버보딩 경고 (PRD F-03-2, R-04)",
        "legal_basis": "상법 및 시행령 겸직 제한 — 최신 법령으로 법무 확인 필요 (PRD §14-5)",
    },
    {
        "key": C.SET_TENURE_LIMIT_YEARS,
        "value": "6",
        "value_type": "int",
        "description": "해당 회사 연속 재직 연수 상한 (PRD R-05)",
        "legal_basis": "상법 시행령 재직 연수 제한 — 최신 법령으로 법무 확인 필요 (PRD §14-5)",
    },
    {
        "key": C.SET_AFFILIATE_TENURE_LIMIT_YEARS,
        "value": "9",
        "value_type": "int",
        "description": "계열회사 합산 재직 연수 상한 (PRD R-05)",
        "legal_basis": "상법 시행령 재직 연수 제한 — 최신 법령으로 법무 확인 필요 (PRD §14-5)",
    },
    {
        "key": C.SET_COOLING_OFF_YEARS,
        "value": "2",
        "value_type": "int",
        "description": "자사·계열사 재직 이력 냉각기간(년) (PRD R-01)",
        "legal_basis": "상법 사외이사 결격사유 — 최신 법령으로 법무 확인 필요 (PRD §14-5)",
    },
    {
        "key": C.SET_SESSION_IDLE_MINUTES,
        "value": "30",
        "value_type": "int",
        "description": "세션 유휴 자동 로그아웃(분) (PRD F-09-13)",
    },
    {
        "key": C.SET_SHARE_LINK_DEFAULT_DAYS,
        "value": "30",
        "value_type": "int",
        "description": "공유 링크 기본 만료 기간(일) (PRD F-09-12, §14-13 결정 대기)",
    },
    {
        "key": C.SET_RETENTION_YEARS,
        "value": "3",
        "value_type": "int",
        "description": "후보자 데이터 보관 기간(년). 경과 시 자동 파기 (PRD §5.2)",
    },
]


def seed_defaults(session) -> int:
    existing = {row[0] for row in session.execute(select(AppSetting.key)).all()}
    created = 0
    for item in DEFAULTS:
        if item["key"] in existing:
            continue
        session.add(AppSetting(**item))
        created += 1
    return created


def get_all() -> dict[str, str]:
    with session_scope() as s:
        return {row.key: row.value for row in s.execute(select(AppSetting)).scalars()}


def get_raw(key: str) -> str | None:
    with session_scope() as s:
        row = s.get(AppSetting, key)
        return row.value if row else None


def get_int(key: str, default: int | None = None) -> int:
    raw = get_raw(key)
    if raw is None:
        if default is None:
            raise KeyError(f"설정값이 없습니다: {key}. AppSetting 시드를 확인하세요.")
        return default
    return int(raw)


def set_value(key: str, value: str, user_id: int | None = None) -> None:
    with session_scope() as s:
        row = s.get(AppSetting, key)
        if row is None:
            raise KeyError(f"등록되지 않은 설정 키입니다: {key}")
        row.value = value
        row.updated_by = user_id
