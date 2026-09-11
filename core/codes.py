"""드롭다운 코드(CodeMaster) 시드 정의 및 조회 (PRD F-01, F-01-7, F-09-2).

UI 는 절대 선택지를 하드코딩하지 않는다. 전부 이 모듈을 통해 DB 에서 읽는다. (불변규칙 3)
extra 필드에는 검색 시 사용할 필터 파라미터를 담는다(예: 연령대의 min/max).
"""

from __future__ import annotations

from sqlalchemy import select

from core import constants as C
from data.models import CodeMaster

# UI 에서 '조건 없음'을 뜻하는 센티널. CodeMaster 에는 저장하지 않는다.
ALL = "__ALL__"
ALL_LABEL = "전체"


def _rows(category: str, items: list[tuple], parent_key: bool = False) -> list[dict]:
    out = []
    for order, item in enumerate(items):
        if parent_key:
            code, label, parent, extra = item
        else:
            parent = None
            if len(item) == 3:
                code, label, extra = item
            else:
                code, label = item
                extra = {}
        out.append(
            {
                "category": category,
                "code": code,
                "label": label,
                "parent_code": parent,
                "sort_order": order,
                "extra": extra or {},
            }
        )
    return out


# ------------------------------------------------------------------ 기본 필터
GENDER = _rows(C.CODE_GENDER, [("M", "남성"), ("F", "여성")])

AGE_BAND = _rows(
    C.CODE_AGE_BAND,
    [
        ("A49", "49세 이하", {"min": None, "max": 49}),
        ("A50", "50~54세", {"min": 50, "max": 54}),
        ("A55", "55~59세", {"min": 55, "max": 59}),
        ("A60", "60~64세", {"min": 60, "max": 64}),
        ("A65", "65~69세", {"min": 65, "max": 69}),
        ("A70", "70세 이상", {"min": 70, "max": None}),
    ],
)

JOB_SCOPE = _rows(
    C.CODE_JOB_SCOPE,
    [
        ("CURRENT", "현직 기준"),
        ("BOTH", "전직 포함"),
        ("PAST", "전직만"),
    ],
)

ROLE_LEVEL = _rows(
    C.CODE_ROLE_LEVEL,
    [
        ("L1", "최고경영자급"),
        ("L2", "임원급(부사장·전무 이상)"),
        ("L3", "임원급(상무·이사)"),
        ("L4", "실무 최고전문가"),
    ],
)

# ------------------------------------------------------------------ 직업 대분류 / 중분류
JOB_L1 = _rows(
    C.CODE_JOB_L1,
    [
        ("CORP", "기업 경영"),
        ("ACAD", "학계"),
        ("LAW", "법조"),
        ("ACCT", "회계·세무"),
        ("GOV", "공직·규제기관"),
        ("FIN", "금융"),
        ("RES", "연구기관"),
        ("PUB", "공공기관·공기업"),
        ("MEDIA", "언론"),
        ("NGO", "협회·NGO"),
        ("ETC", "기타"),
    ],
)

_JOB_L2_ITEMS = [
    ("CORP_CEO", "CEO·대표이사", "CORP", {}),
    ("CORP_CFO", "CFO", "CORP", {}),
    ("CORP_COO", "COO·CTO", "CORP", {}),
    ("CORP_DIR", "기타 등기임원", "CORP", {}),
    ("CORP_EXE", "미등기 집행임원", "CORP", {}),
    ("CORP_OSD", "사외이사 전업", "CORP", {}),
    ("ACAD_PROF", "교수", "ACAD", {}),
    ("ACAD_EMER", "석좌·명예교수", "ACAD", {}),
    ("ACAD_ADMIN", "대학 보직자(총장·학장)", "ACAD", {}),
    ("LAW_JUDGE", "판사", "LAW", {}),
    ("LAW_PROS", "검사", "LAW", {}),
    ("LAW_PART", "변호사(로펌 파트너)", "LAW", {}),
    ("LAW_INHOUSE", "사내변호사", "LAW", {}),
    ("ACCT_CPA", "공인회계사(회계법인 파트너)", "ACCT", {}),
    ("ACCT_TAX", "세무사", "ACCT", {}),
    ("ACCT_AUDIT", "내부감사 책임자", "ACCT", {}),
    ("GOV_MOEF", "기획재정부", "GOV", {}),
    ("GOV_FSC", "금융위·금감원", "GOV", {}),
    ("GOV_FTC", "공정거래위원회", "GOV", {}),
    ("GOV_NTS", "국세청", "GOV", {}),
    ("GOV_MOTIE", "산업통상자원부", "GOV", {}),
    ("GOV_CENTRAL", "기타 중앙부처", "GOV", {}),
    ("GOV_LOCAL", "지방자치단체", "GOV", {}),
    ("FIN_BANK", "은행", "FIN", {}),
    ("FIN_SEC", "증권", "FIN", {}),
    ("FIN_AM", "자산운용", "FIN", {}),
    ("FIN_PE", "PE·VC", "FIN", {}),
    ("FIN_INS", "보험", "FIN", {}),
    ("RES_GOV", "정부출연연구기관", "RES", {}),
    ("RES_PRIV", "민간 연구소", "RES", {}),
    ("PUB_HEAD", "공공기관장", "PUB", {}),
    ("PUB_EXEC", "공공기관 임원", "PUB", {}),
    ("MEDIA_EXEC", "언론사 임원", "MEDIA", {}),
    ("MEDIA_SENIOR", "논설·편집위원", "MEDIA", {}),
    ("NGO_HEAD", "협회·단체장", "NGO", {}),
    ("NGO_EXEC", "협회·단체 임원", "NGO", {}),
    ("ETC_OTHER", "기타", "ETC", {}),
]
JOB_L2 = _rows(C.CODE_JOB_L2, _JOB_L2_ITEMS, parent_key=True)

# ------------------------------------------------------------------ 전문분야 택소노미 (PRD §6.4)
_EXPERTISE_TAXONOMY: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("EXP_FIN", "재무·회계"): [
        ("EXP_FIN_01", "재무전략"),
        ("EXP_FIN_02", "회계·공시"),
        ("EXP_FIN_03", "세무"),
        ("EXP_FIN_04", "자금·IR"),
    ],
    ("EXP_AUD", "감사·내부통제"): [
        ("EXP_AUD_01", "내부감사"),
        ("EXP_AUD_02", "내부회계관리제도"),
        ("EXP_AUD_03", "부정방지·포렌식"),
    ],
    ("EXP_LAW", "법률·규제"): [
        ("EXP_LAW_01", "회사법·지배구조"),
        ("EXP_LAW_02", "공정거래"),
        ("EXP_LAW_03", "금융규제"),
        ("EXP_LAW_04", "노동법"),
        ("EXP_LAW_05", "지식재산"),
        ("EXP_LAW_06", "국제통상"),
        ("EXP_LAW_07", "송무"),
    ],
    ("EXP_CAP", "자본시장·M&A"): [
        ("EXP_CAP_01", "M&A"),
        ("EXP_CAP_02", "PE·투자"),
        ("EXP_CAP_03", "구조조정"),
        ("EXP_CAP_04", "상장·자본조달"),
    ],
    ("EXP_STR", "경영전략"): [
        ("EXP_STR_01", "전사전략"),
        ("EXP_STR_02", "신사업"),
        ("EXP_STR_03", "사업포트폴리오"),
        ("EXP_STR_04", "턴어라운드"),
    ],
    ("EXP_GLB", "글로벌"): [
        ("EXP_GLB_01", "해외사업"),
        ("EXP_GLB_02", "지역 전문성 – 미주"),
        ("EXP_GLB_03", "지역 전문성 – 중국"),
        ("EXP_GLB_04", "지역 전문성 – 일본"),
        ("EXP_GLB_05", "지역 전문성 – 유럽"),
        ("EXP_GLB_06", "지역 전문성 – 동남아"),
        ("EXP_GLB_07", "지역 전문성 – 중동"),
    ],
    ("EXP_MKT", "마케팅·고객"): [
        ("EXP_MKT_01", "브랜드"),
        ("EXP_MKT_02", "유통·채널"),
        ("EXP_MKT_03", "고객경험"),
    ],
    ("EXP_TEC", "기술·R&D"): [
        ("EXP_TEC_01", "산업별 기술 전문성"),
        ("EXP_TEC_02", "연구개발 관리"),
        ("EXP_TEC_03", "제품개발"),
    ],
    ("EXP_DIG", "디지털·IT"): [
        ("EXP_DIG_01", "IT전략"),
        ("EXP_DIG_02", "데이터·AI"),
        ("EXP_DIG_03", "클라우드"),
        ("EXP_DIG_04", "디지털 전환"),
    ],
    ("EXP_SEC", "사이버보안·개인정보"): [
        ("EXP_SEC_01", "정보보호"),
        ("EXP_SEC_02", "개인정보보호"),
        ("EXP_SEC_03", "보안 거버넌스"),
    ],
    ("EXP_ESG", "ESG·지속가능경영"): [
        ("EXP_ESG_01", "ESG 전략·공시"),
        ("EXP_ESG_02", "환경·기후"),
        ("EXP_ESG_03", "사회·인권"),
        ("EXP_ESG_04", "지배구조"),
    ],
    ("EXP_HR", "인사·조직"): [
        ("EXP_HR_01", "HR 전략"),
        ("EXP_HR_02", "보상"),
        ("EXP_HR_03", "조직문화"),
        ("EXP_HR_04", "노사관계"),
    ],
    ("EXP_RSK", "리스크관리"): [
        ("EXP_RSK_01", "전사리스크"),
        ("EXP_RSK_02", "재무리스크"),
        ("EXP_RSK_03", "컴플라이언스"),
        ("EXP_RSK_04", "위기관리"),
    ],
    ("EXP_OPS", "운영·공급망"): [
        ("EXP_OPS_01", "생산·품질"),
        ("EXP_OPS_02", "구매·조달"),
        ("EXP_OPS_03", "물류"),
        ("EXP_OPS_04", "안전보건(중대재해)"),
    ],
    ("EXP_PUB", "공공·정책"): [
        ("EXP_PUB_01", "정책·규제 대응"),
        ("EXP_PUB_02", "대관"),
        ("EXP_PUB_03", "공공조달"),
    ],
}

EXPERTISE_L1 = _rows(
    C.CODE_EXPERTISE_L1, [(code, label) for (code, label) in _EXPERTISE_TAXONOMY.keys()]
)
EXPERTISE_L2 = _rows(
    C.CODE_EXPERTISE_L2,
    [
        (code, label, parent, {})
        for (parent, _), children in _EXPERTISE_TAXONOMY.items()
        for (code, label) in children
    ],
    parent_key=True,
)

# ------------------------------------------------------------------ 기타 필터
INDUSTRY = _rows(
    C.CODE_INDUSTRY,
    [
        ("IND_SEMI", "반도체·전자"),
        ("IND_AUTO", "자동차·모빌리티"),
        ("IND_CHEM", "화학·소재"),
        ("IND_BIO", "바이오·헬스케어"),
        ("IND_FIN", "금융"),
        ("IND_RETAIL", "유통·소비재"),
        ("IND_CONST", "건설·부동산"),
        ("IND_ENERGY", "에너지·유틸리티"),
        ("IND_IT", "IT·플랫폼"),
        ("IND_TELCO", "통신"),
        ("IND_HEAVY", "조선·중공업"),
        ("IND_LOGI", "물류"),
        ("IND_ETC", "기타"),
    ],
)

NATIONALITY = _rows(
    C.CODE_NATIONALITY,
    [
        ("KR", "대한민국"),
        ("US", "미국"),
        ("JP", "일본"),
        ("CN", "중국"),
        ("GB", "영국"),
        ("DE", "독일"),
        ("FR", "프랑스"),
        ("SG", "싱가포르"),
        ("ETC", "기타"),
    ],
)

CONCURRENT = _rows(
    C.CODE_CONCURRENT,
    [
        ("C0", "0개", {"min": 0, "max": 0}),
        ("C1", "1개", {"min": 1, "max": 1}),
        ("C2", "2개", {"min": 2, "max": 2}),
        ("C3", "3개 이상", {"min": 3, "max": None}),
    ],
)

TERM_REMAIN = _rows(
    C.CODE_TERM_REMAIN,
    [
        ("T6", "6개월 이내 만료", {"max_months": 6}),
        ("T12", "1년 이내 만료", {"max_months": 12}),
        ("TOVER", "1년 초과", {"min_months": 12}),
    ],
)

SCREENING_FILTER = _rows(
    C.CODE_SCREENING,
    [
        ("CLEAN", "이슈 없음만", {"allow": [C.SCREEN_PASS]}),
        ("WARN_OK", "경고 포함", {"allow": [C.SCREEN_PASS, C.SCREEN_WARN]}),
    ],
)

REPUTATION_FILTER = _rows(
    C.CODE_REPUTATION,
    [("NO_NEG", "확인된 부정 이슈 없음만", {"exclude_verified_negative": True})],
)

REGION = _rows(
    C.CODE_REGION,
    [
        ("R_CAPITAL", "수도권"),
        ("R_YEONGNAM", "영남"),
        ("R_HONAM", "호남"),
        ("R_CHUNGCHEONG", "충청"),
        ("R_GANGWON", "강원·제주"),
        ("R_OVERSEAS", "해외"),
    ],
)

FRESHNESS = _rows(
    C.CODE_FRESHNESS,
    [
        ("F6", "최근 6개월 내 갱신", {"months": 6}),
        ("F12", "최근 12개월 내 갱신", {"months": 12}),
    ],
)

SORT = _rows(
    C.CODE_SORT,
    [
        ("FIT", "적합도 점수순"),
        ("FRESH", "데이터 최신순"),
        ("FEWEST", "겸직 적은 순"),
        ("AGE_ASC", "연령 낮은 순"),
    ],
)

# '전체'는 시스템 상한(AppSetting)을 적용하므로 value=None 으로 둔다 (PRD F-01-8)
RESULT_LIMIT = _rows(
    C.CODE_RESULT_LIMIT,
    [
        ("N10", "10명", {"value": 10}),
        ("N20", "20명", {"value": 20}),
        ("N30", "30명", {"value": 30}),
        ("N50", "50명", {"value": 50}),
        ("N100", "100명", {"value": 100}),
        ("N200", "200명", {"value": 200}),
        ("NALL", "전체", {"value": None}),
    ],
)

ALL_CODE_ROWS: list[dict] = (
    GENDER
    + AGE_BAND
    + JOB_SCOPE
    + ROLE_LEVEL
    + JOB_L1
    + JOB_L2
    + EXPERTISE_L1
    + EXPERTISE_L2
    + INDUSTRY
    + NATIONALITY
    + CONCURRENT
    + TERM_REMAIN
    + SCREENING_FILTER
    + REPUTATION_FILTER
    + REGION
    + FRESHNESS
    + SORT
    + RESULT_LIMIT
)


# ------------------------------------------------------------------ 시드 / 조회

def seed_codes(session) -> int:
    existing = {
        (row.category, row.code) for row in session.execute(select(CodeMaster)).scalars()
    }
    created = 0
    for row in ALL_CODE_ROWS:
        if (row["category"], row["code"]) in existing:
            continue
        session.add(CodeMaster(**row))
        created += 1
    return created


def load_codes(category: str, parent_code: str | None = None) -> list[CodeMaster]:
    """활성 코드를 정렬 순서대로 반환.

    parent_code 를 주면 해당 상위코드의 하위만 반환한다(cascading, PRD F-01-2).
    """
    from data.session import session_scope

    stmt = (
        select(CodeMaster)
        .where(CodeMaster.category == category, CodeMaster.is_active.is_(True))
        .order_by(CodeMaster.sort_order)
    )
    if parent_code is not None:
        stmt = stmt.where(CodeMaster.parent_code == parent_code)
    with session_scope() as s:
        return list(s.execute(stmt).scalars())


def code_map(category: str) -> dict[str, str]:
    """code -> label"""
    return {c.code: c.label for c in load_codes(category)}


def label_of(category: str, code: str | None) -> str:
    if code is None or code == ALL:
        return ALL_LABEL
    return code_map(category).get(code, code)


def extra_of(category: str, code: str) -> dict:
    for c in load_codes(category):
        if c.code == code:
            return c.extra or {}
    return {}
