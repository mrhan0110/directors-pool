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
    {
        "key": C.SET_SHARE_LINK_MAX_DAYS,
        "value": "90",
        "value_type": "int",
        "description": "공유 링크 최대 허용 기간(일) (PRD §14-13 결정 대기)",
    },
    # ---------------- 자사 정보 (더미 기본값 — 운영 전 실제 값으로 교체)
    {
        "key": C.SET_OWN_COMPANY,
        "value": "가상홀딩스",
        "value_type": "str",
        "description": "자사 법인명. R-01·R-05 판정 기준",
    },
    {
        "key": C.SET_AFFILIATES,
        "value": "가상홀딩스캐피탈,가상홀딩스물산",
        "value_type": "list",
        "description": "계열회사 목록(콤마 구분). R-01·R-05 판정 기준",
    },
    {
        "key": C.SET_MAJOR_SHAREHOLDERS,
        "value": "가상홀딩스재단,가상투자조합",
        "value_type": "list",
        "description": "최대주주·주요주주 및 특수관계인(콤마 구분). R-02 판정 기준",
    },
    {
        "key": C.SET_CONFLICT_ORGS,
        "value": "예시회계법인,법무법인 예시",
        "value_type": "list",
        "description": "주요 거래처·외부감사인·법률자문사 등 이해상충 기관(콤마 구분). R-03 판정 기준",
    },
    {
        "key": C.SET_TOTAL_ASSETS_KRW,
        "value": "2500000000000",
        "value_type": "int",
        "description": "자사 직전 사업연도말 자산총액(원). R-08 판정 기준",
    },
    {
        "key": C.SET_GENDER_RULE_ASSET_THRESHOLD,
        "value": "2000000000000",
        "value_type": "int",
        "description": "이사회 특정 성 단독 구성 금지 대상 자산총액 기준(원) (PRD R-08)",
        "legal_basis": "자본시장법 이사회 성별 구성 규정 — 최신 법령으로 법무 확인 필요 (PRD §14-5)",
    },
    {
        "key": C.SET_BOARD_FEMALE_COUNT,
        "value": "0",
        "value_type": "int",
        "description": "자사 현 이사회 여성 이사 수. R-08 판정 기준",
    },
    {
        "key": C.SET_BOARD_SKILL_GAPS,
        "value": "EXP_SEC_01,EXP_ESG_01,EXP_DIG_02",
        "value_type": "list",
        "description": "자사 이사회 스킬 매트릭스 공백 전문분야 코드(콤마). 적합도 산정 기준 (PRD §14-8 결정 대기)",
    },
    {
        "key": C.SET_ATTENDANCE_WARN_RATE,
        "value": "0.75",
        "value_type": "float",
        "description": "타사 이사회 출석률이 이 값 미만이면 성실성 확인 필요 (PRD F-03 (7)-5)",
    },
    {
        "key": C.SET_R06_FAIL_CATEGORIES,
        "value": "규제 제재,형사 판결",
        "value_type": "list",
        "description": "확인·확정 시 결격 가능(🔴)으로 판정할 부정 이슈 유형. 그 외 유형은 확인 필요(🟡) (PRD R-06)",
        "legal_basis": "상법 사외이사 결격사유(금고 이상 형, 금융관련법령 제재) — 법무 확인 필요",
    },
    {
        "key": C.SET_AUDIT_EXPERT_CERTS,
        "value": "공인회계사",
        "value_type": "list",
        "description": "감사위원 회계·재무 전문가 요건 근거로 인정할 자격 (PRD R-07)",
        "legal_basis": "상법 시행령 감사위원 회계·재무 전문가 요건 — 법무 확인 필요",
    },
    {
        "key": C.SET_AUDIT_EXPERT_JOBS,
        "value": "ACCT_CPA,ACCT_AUDIT,CORP_CFO,GOV_FSC",
        "value_type": "list",
        "description": "감사위원 요건 근거로 인정할 직업 중분류 코드 (PRD R-07)",
    },
    {
        "key": C.SET_AUDIT_EXPERT_EXPERTISE,
        "value": "EXP_FIN,EXP_AUD",
        "value_type": "list",
        "description": "감사위원 요건 근거로 인정할 전문분야 코드 접두어 (PRD R-07)",
    },
    # ---------------- 적합도 가중치 (PRD F-06)
    {"key": C.SET_W_EXPERTISE, "value": "40", "value_type": "int",
     "description": "적합도 — 전문분야 매칭도 가중치"},
    {"key": C.SET_W_SKILL_GAP, "value": "20", "value_type": "int",
     "description": "적합도 — 이사회 스킬 갭 보완도 가중치"},
    {"key": C.SET_W_CAREER, "value": "15", "value_type": "int",
     "description": "적합도 — 경력 수준·규모 적합도 가중치"},
    {"key": C.SET_W_AVAILABILITY, "value": "15", "value_type": "int",
     "description": "적합도 — 가용성(겸직·출석률) 가중치"},
    {"key": C.SET_W_RISK, "value": "10", "value_type": "int",
     "description": "적합도 — 리스크 감점 최대치"},
    # ---------------- 출처 최신성 (PRD F-05-4)
    {
        "key": C.SET_NEWS_FRESH_YEARS,
        "value": "3",
        "value_type": "int",
        "description": "언론 출처 최신성 기준(년). 초과 시 '구 정보' 배지",
    },
    {
        "key": C.SET_DISCLOSURE_FRESH_DAYS,
        "value": "460",
        "value_type": "int",
        "description": "공시자료 최신성 기준(발행일로부터 일). 다음 사업보고서가 나왔을 시점을 넘기면 '구 정보' 배지",
    },
    {
        "key": C.SET_WEB_FRESH_DAYS,
        "value": "365",
        "value_type": "int",
        "description": "기관 홈페이지 출처 최신성 기준(수집일로부터 일). 초과 시 '구 정보' 배지",
    },
    {
        "key": C.SET_IDENTITY_MERGE_THRESHOLD,
        "value": "0.8",
        "value_type": "float",
        "description": "동명이인 자동 결합 최소 신뢰도(0~1). 미만이면 수기 확인 큐로 (PRD §11)",
    },
    {
        "key": C.SET_DART_TARGET_COMPANIES,
        "value": "",
        "value_type": "list",
        "description": "DART 실제 수집 대상 'corp_code:회사명' 쌍(콤마 구분). "
                       "초기 모집단 범위는 결정 대기(PRD §14-1) — 결정 후 이 값을 채운다",
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


def list_all() -> list[AppSetting]:
    """관리자 화면 표시용 전체 행(설명·법령근거·최종변경 포함)."""
    with session_scope() as s:
        return list(s.execute(select(AppSetting).order_by(AppSetting.key)).scalars())


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


def get_str(key: str, default: str | None = None) -> str:
    raw = get_raw(key)
    if raw is None:
        if default is None:
            raise KeyError(f"설정값이 없습니다: {key}. AppSetting 시드를 확인하세요.")
        return default
    return raw


def get_float(key: str, default: float | None = None) -> float:
    raw = get_raw(key)
    if raw is None:
        if default is None:
            raise KeyError(f"설정값이 없습니다: {key}. AppSetting 시드를 확인하세요.")
        return default
    return float(raw)


def get_list(key: str) -> list[str]:
    """콤마 구분 목록. 빈 값이면 빈 리스트."""
    raw = get_raw(key) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def validate(value_type: str, value: str) -> str:
    """관리자 입력값 검증. 잘못된 값이 룰 판정을 깨뜨리지 않게 저장 전에 막는다."""
    value = value.strip()
    if value_type == "int":
        int(value)
    elif value_type == "float":
        float(value)
    return value


def set_value(key: str, value: str, user_id: int | None = None) -> str:
    """값을 바꾸고 이전 값을 반환한다. 호출부는 AuditLog 에 변경 이력을 남긴다."""
    with session_scope() as s:
        row = s.get(AppSetting, key)
        if row is None:
            raise KeyError(f"등록되지 않은 설정 키입니다: {key}")
        before = row.value
        row.value = validate(row.value_type, value)
        row.updated_by = user_id
        return before
