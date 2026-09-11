"""도메인 상수.

여기에는 '코드 구조'만 둔다. 법령에 연동된 임계값(겸직 한도, 재직 연수 상한 등)은
절대 이 파일에 두지 않는다. AppSetting 테이블에서 읽는다. (PRD §5 상단, 불변규칙 4)
"""

from __future__ import annotations

# ---------------------------------------------------------------- 역할 (PRD §3.1, F-09-11)
ROLE_STAFF = "담당자"
ROLE_HEAD = "사무국장"
ROLE_LEGAL = "법무"
ROLE_ADMIN = "관리자"
ROLE_VIEWER = "외부뷰어"

ALL_ROLES = (ROLE_STAFF, ROLE_HEAD, ROLE_LEGAL, ROLE_ADMIN, ROLE_VIEWER)

ROLE_DESCRIPTIONS = {
    ROLE_STAFF: "검색·조회·POOL 편집·리포트 출력",
    ROLE_HEAD: "담당자 권한 + 승인",
    ROLE_LEGAL: "조회 + 결격·이해상충 검증 결과 입력",
    ROLE_ADMIN: "전체 (코드·룰·사용자·감사로그 관리)",
    ROLE_VIEWER: "지정 POOL 읽기 전용 (다운로드 불가, 접근 만료일 적용)",
}

# ---------------------------------------------------------------- 프로파일 검수 상태 (PRD F-08-1)
PROFILE_UNREVIEWED = "미검수"
PROFILE_REVIEWED = "검수완료"

# ---------------------------------------------------------------- 스크리닝 판정 (PRD §5.1, F-06)
SCREEN_PASS = "pass"
SCREEN_WARN = "warn"
SCREEN_FAIL = "fail"
# 참고 정보(R-07 감사위원 요건, R-08 다양성). 후보의 대표 상태를 나쁘게 만들지 않는다.
SCREEN_INFO = "info"

SCREEN_BADGE = {
    SCREEN_PASS: "🟢 이슈 없음",
    SCREEN_WARN: "🟡 확인 필요",
    SCREEN_FAIL: "🔴 결격 가능",
    SCREEN_INFO: "ℹ️ 참고",
}
# 목록 정렬 시 결격 후보를 하단으로 분리하기 위한 순위 (PRD F-06). info 는 pass 보다 낮다.
SCREEN_ORDER = {SCREEN_INFO: -1, SCREEN_PASS: 0, SCREEN_WARN: 1, SCREEN_FAIL: 2}

# 스크리닝 룰 정의 (PRD §5.1). 판정 로직은 core/screening.py.
SCREENING_RULES = {
    "R-01": "회사·계열회사의 상근 임직원 또는 냉각기간 내 재직 이력",
    "R-02": "최대주주·주요주주 본인 및 특수관계인 여부",
    "R-03": "주요 거래처·법률/회계 자문사 등 이해상충 관계",
    "R-04": "타 회사 사외이사 등 겸직 수 한도 초과",
    "R-05": "해당 회사 재직 연수 상한 초과(연속 / 계열 합산)",
    "R-06": "금고 이상 형 확정, 금융관련법령 제재, 부정거래 이력",
    "R-07": "감사위원 요건(회계·재무 전문가 여부) 충족",
    "R-08": "이사회 특정 성(性) 단독 구성 금지 대상 해당 여부",
}

# ---------------------------------------------------------------- 출처 신뢰도 등급 (PRD F-05)
SOURCE_TIER_A = "A"  # 공시·공적자료
SOURCE_TIER_B = "B"  # 기관 공식 정보
SOURCE_TIER_C = "C"  # 언론
SOURCE_TIER_ORDER = {SOURCE_TIER_A: 0, SOURCE_TIER_B: 1, SOURCE_TIER_C: 2}

# 수집 단계에서 원천 차단하는 도메인 패턴 (PRD F-05 '제외' 목록, 불변규칙 7).
# 2단계 collectors 가 이 목록을 강제한다.
SOURCE_DOMAIN_BLOCKLIST = (
    "blog.naver.com",
    "cafe.naver.com",
    "tistory.com",
    "brunch.co.kr",
    "dcinside.com",
    "fmkorea.com",
    "clien.net",
    "ppomppu.co.kr",
    "blind.impact.com",
    "teamblind.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "threads.net",
    "youtube.com",
    "wikipedia.org",
    "namu.wiki",
)

# ---------------------------------------------------------------- POOL 상태 (PRD F-07)
POOL_MEMBER_STATES = (
    "후보 등록",
    "1차 검토",
    "법무 검증",
    "사추위 보고",
    "접촉",
    "최종후보",
    "보류",
    "제외",
)
POOL_MEMBER_STATES_REQUIRING_REASON = ("제외", "보류")

# ---------------------------------------------------------------- CodeMaster 카테고리 (PRD F-01)
# 검색 드롭다운은 전부 이 카테고리를 통해 DB 에서 로드한다. 하드코딩 금지 (불변규칙 3)
CODE_GENDER = "GENDER"
CODE_AGE_BAND = "AGE_BAND"
CODE_JOB_SCOPE = "JOB_SCOPE"
CODE_JOB_L1 = "JOB_L1"
CODE_JOB_L2 = "JOB_L2"
CODE_ROLE_LEVEL = "ROLE_LEVEL"
CODE_EXPERTISE_L1 = "EXPERTISE_L1"
CODE_EXPERTISE_L2 = "EXPERTISE_L2"
CODE_INDUSTRY = "INDUSTRY"
CODE_NATIONALITY = "NATIONALITY"
CODE_CONCURRENT = "CONCURRENT_COUNT"
CODE_TERM_REMAIN = "TERM_REMAIN"
CODE_SCREENING = "SCREENING_FILTER"
CODE_REPUTATION = "REPUTATION_FILTER"
CODE_REGION = "REGION"
CODE_FRESHNESS = "DATA_FRESHNESS"
CODE_SORT = "SORT"
CODE_RESULT_LIMIT = "RESULT_LIMIT"

# ---------------------------------------------------------------- AppSetting 키 (불변규칙 4)
SET_RESULT_LIMIT_DEFAULT = "search.result_limit.default"
SET_RESULT_LIMIT_SYSTEM_MAX = "search.result_limit.system_max"
SET_RESULT_LIMIT_VIEWER_MAX = "search.result_limit.viewer_max"
SET_PAGE_SIZE = "search.page_size"
SET_CAREER_LOOKBACK_YEARS = "profile.career_lookback_years"
SET_TERM_ALERT_MONTHS = "profile.term_alert_months"
SET_CONCURRENT_LIMIT = "rule.concurrent_directorship_limit"
SET_TENURE_LIMIT_YEARS = "rule.tenure_limit_years"
SET_AFFILIATE_TENURE_LIMIT_YEARS = "rule.affiliate_tenure_limit_years"
SET_COOLING_OFF_YEARS = "rule.cooling_off_years"
SET_SESSION_IDLE_MINUTES = "auth.session_idle_minutes"
SET_SHARE_LINK_DEFAULT_DAYS = "share.default_expiry_days"
SET_SHARE_LINK_MAX_DAYS = "share.max_expiry_days"
SET_RETENTION_YEARS = "privacy.retention_years"

# 자사 정보 — 스크리닝 룰의 판정 기준 (PRD §5.1). 전부 관리자 화면에서 수정한다.
SET_OWN_COMPANY = "org.own_company"
SET_AFFILIATES = "org.affiliates"
SET_MAJOR_SHAREHOLDERS = "org.major_shareholders"
SET_CONFLICT_ORGS = "org.conflict_orgs"
SET_TOTAL_ASSETS_KRW = "org.total_assets_krw"
SET_BOARD_FEMALE_COUNT = "org.board_female_count"
SET_BOARD_SKILL_GAPS = "org.board_skill_gaps"
SET_GENDER_RULE_ASSET_THRESHOLD = "rule.gender_rule_asset_threshold_krw"
SET_ATTENDANCE_WARN_RATE = "rule.attendance_warn_rate"

# 적합도 가중치 (PRD F-06)
SET_W_EXPERTISE = "score.weight.expertise_match"
SET_W_SKILL_GAP = "score.weight.skill_gap"
SET_W_CAREER = "score.weight.career_level"
SET_W_AVAILABILITY = "score.weight.availability"
SET_W_RISK = "score.weight.risk_penalty"

# 출처 최신성 (PRD F-05-4)
SET_NEWS_FRESH_YEARS = "source.news_fresh_years"
SET_WEB_FRESH_DAYS = "source.web_fresh_days"

# 인물 식별 — 이 점수 미만이면 자동 결합하지 않고 수기 확인 큐로 (PRD §11)
SET_IDENTITY_MERGE_THRESHOLD = "identity.auto_merge_threshold"

# ---------------------------------------------------------------- AccessLog 액션 (PRD F-09-22)
ACT_LOGIN = "login"
ACT_LOGOUT = "logout"
ACT_VIEW = "view"
ACT_SEARCH = "search"
ACT_EXPORT = "export"
ACT_SHARE_ISSUE = "share_issue"
ACT_SHARE_REVOKE = "share_revoke"
ACT_SHARE_ACCESS = "share_access"
ACT_DENIED = "access_denied"

# ---------------------------------------------------------------- 검수 (PRD F-08)
REVIEW_APPROVE = "승인"
REVIEW_EDIT = "수정"
REVIEW_DELETE = "삭제"

# ReviewQueue 유형
QUEUE_IDENTITY = "동명이인 확인"
QUEUE_CONFLICT = "충돌 알림"  # 수동 수정 항목을 자동 갱신이 바꾸려 할 때 (F-08-4)
