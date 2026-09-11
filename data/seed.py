"""합성 더미데이터 생성기.

⚠️ 실존 인물 데이터를 절대 넣지 않는다 (불변규칙 6).
이름은 '가상001 …' 형태로 생성해 실명과 혼동될 가능성을 없앤다.
모든 URL 은 example.com 기반 가짜 URL 이다.

실행: python -m data.seed            (기존 DB 유지, 없는 것만 추가)
      python -m data.seed --reset    (전체 삭제 후 재생성)
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from core import codes as CODES
from core import constants as C
from core import expertise as EXP
from core import settings
from data.models import (
    Achievement,
    AppUser,
    Directorship,
    Person,
    PersonIndustry,
    Pool,
    PoolMember,
    Position,
    Reputation,
    ScreeningResult,
    Source,
)
from data.session import init_db, session_scope

SEED = 20260911
# 테스트에서는 소량만 생성한다 (SEED_PERSON_COUNT)
PERSON_COUNT = int(os.getenv("SEED_PERSON_COUNT", "200"))
TODAY = date.today()

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권"]
GIVEN = ["서연", "지훈", "민재", "하늘", "가온", "도윤", "수아", "예린", "성호", "다은",
         "지원", "현우", "나윤", "태경", "은우", "지안", "채원", "시우", "유진", "상현"]

COMPANIES = [
    "가상전자", "가상화학", "가상금융지주", "가상바이오", "가상중공업", "가상유통",
    "가상건설", "가상에너지", "가상모빌리티", "가상소재", "가상통신", "가상물류",
    "가상반도체", "가상제약", "가상식품", "가상해운",
]
ORGS_BY_JOB = {
    "CORP": COMPANIES,
    "ACAD": ["가상대학교", "가상과학기술원", "가상여자대학교"],
    "LAW": ["법무법인 가상", "법무법인 예시", "서울가상지방법원", "가상지방검찰청"],
    "ACCT": ["가상회계법인", "예시회계법인", "가상세무법인"],
    "GOV": ["기획재정부(가상)", "금융감독원(가상)", "공정거래위원회(가상)", "국세청(가상)"],
    "FIN": ["가상은행", "가상증권", "가상자산운용", "가상캐피탈", "가상생명"],
    "RES": ["가상경제연구원", "가상산업연구원"],
    "PUB": ["가상공사", "가상진흥원"],
    "MEDIA": ["가상일보", "가상경제신문"],
    "NGO": ["가상경영자총협회", "가상지속가능경영원"],
    "ETC": ["가상컨설팅"],
}

TITLES_BY_LEVEL = {
    "L1": ["대표이사 사장", "대표이사 부회장", "총장", "원장", "청장(가상)"],
    "L2": ["부사장", "전무", "법원장(가상)", "검사장(가상)", "대표변호사"],
    "L3": ["상무", "이사", "감사", "본부장"],
    "L4": ["수석연구원", "선임전문위원", "파트너"],
}

PUBLISHERS_A = ["금융감독원 전자공시시스템", "한국거래소 KIND", "관보(가상)"]
PUBLISHERS_B = ["가상전자 공식 홈페이지", "가상대학교 교수 프로필", "법무법인 가상 공식 프로필"]
PUBLISHERS_C = ["가상일보", "가상경제신문", "가상뉴스통신"]


def _rand_date(rng: random.Random, start_year: int, end_year: int) -> date:
    year = rng.randint(start_year, end_year)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return date(year, month, day)


def _make_source(rng: random.Random, tier: str, idx: int) -> Source:
    if tier == C.SOURCE_TIER_A:
        publisher = rng.choice(PUBLISHERS_A)
        title = "가상주식회사 2025년 사업보고서 — Ⅷ. 임원 및 직원 등에 관한 사항"
        url = f"https://dart.example.com/report/{idx:06d}"
        published = _rand_date(rng, 2025, 2026)
    elif tier == C.SOURCE_TIER_B:
        publisher = rng.choice(PUBLISHERS_B)
        title = "경영진 소개"
        url = f"https://company.example.com/about/management/{idx:06d}"
        published = _rand_date(rng, 2024, 2026)
    else:
        publisher = rng.choice(PUBLISHERS_C)
        title = f"가상 기사 제목 {idx:04d}"
        url = f"https://news.example.com/article/{idx:06d}"
        published = _rand_date(rng, 2023, 2026)
    return Source(
        publisher=publisher,
        doc_title=title,
        published_date=published,
        url=url,
        source_tier=tier,
        quote_snippet="(더미데이터) 근거 인용 문장입니다.",
        snapshot_path=f"./storage/snapshots/dummy/{idx:06d}.html",
    )


def _seed_users(session) -> None:
    existing = {row for row in session.execute(select(AppUser.email)).scalars()}
    accounts = [
        ("staff@example.com", "가상 담당자", C.ROLE_STAFF, None),
        ("head@example.com", "가상 사무국장", C.ROLE_HEAD, None),
        ("legal@example.com", "가상 법무담당", C.ROLE_LEGAL, None),
        ("admin@example.com", "가상 관리자", C.ROLE_ADMIN, None),
        ("viewer@example.com", "가상 외부위원", C.ROLE_VIEWER, TODAY + timedelta(days=30)),
        # 만료된 외부뷰어 — 접근 만료 동작 확인용 (PRD F-09-12)
        ("viewer-expired@example.com", "가상 외부위원(만료)", C.ROLE_VIEWER, TODAY - timedelta(days=1)),
    ]
    for email, name, role, expires in accounts:
        if email in existing:
            continue
        session.add(
            AppUser(
                email=email,
                display_name=name,
                role=role,
                org_affiliation="가상조직",
                expires_at=expires,
            )
        )


def _seed_people(session, rng: random.Random) -> int:
    if session.execute(select(Person.person_id).limit(1)).first():
        return 0

    job_l1_codes = [r["code"] for r in CODES.JOB_L1]
    job_l2_by_parent: dict[str, list[str]] = {}
    for r in CODES.JOB_L2:
        job_l2_by_parent.setdefault(r["parent_code"], []).append(r["code"])
    exp_l2_codes = [r["code"] for r in CODES.EXPERTISE_L2]
    industry_codes = [r["code"] for r in CODES.INDUSTRY]
    region_codes = [r["code"] for r in CODES.REGION]
    source_counter = 0

    for i in range(1, PERSON_COUNT + 1):
        surname = rng.choice(SURNAMES)
        given = rng.choice(GIVEN)
        gender = "F" if rng.random() < 0.32 else "M"
        birth_year = rng.randint(TODAY.year - 74, TODAY.year - 45)

        nationalities = ["KR"]
        multi = False
        if rng.random() < 0.06:
            nationalities = [rng.choice(["US", "JP", "GB", "SG", "DE"])]
        if rng.random() < 0.03:
            nationalities = ["KR", "US"]
            multi = True

        person = Person(
            name_ko=f"가상{i:03d} {surname}{given}",
            name_en=f"TEST-CANDIDATE-{i:03d}",
            gender=gender,
            birth_year=birth_year,
            age_estimated_yn=True,
            nationality=nationalities,
            nationality_primary=nationalities[0],
            multi_nationality_yn=multi,
            residence_region=rng.choice(region_codes),
            education=[{"school": "가상대학교", "degree": rng.choice(["학사", "석사", "박사"]),
                        "major": rng.choice(["경영학", "경제학", "법학", "회계학", "전자공학", "화학공학"])}],
            certifications=rng.sample(["공인회계사", "변호사", "세무사", "CFA", "정보보안기사"],
                                      k=rng.choice([0, 0, 1, 1, 2])),
            profile_status=C.PROFILE_REVIEWED if rng.random() < 0.25 else C.PROFILE_UNREVIEWED,
            retention_until=TODAY + timedelta(days=365 * 3),
            updated_at=datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 400)),
        )
        session.add(person)
        session.flush()

        # ---------------- 출처
        source_counter += 1
        src_a = _make_source(rng, C.SOURCE_TIER_A, source_counter)
        source_counter += 1
        src_b = _make_source(rng, C.SOURCE_TIER_B, source_counter)
        source_counter += 1
        src_c = _make_source(rng, C.SOURCE_TIER_C, source_counter)
        session.add_all([src_a, src_b, src_c])
        session.flush()

        # ---------------- 경력 3~8건
        main_l1 = rng.choice(job_l1_codes)
        n_pos = rng.randint(3, 8)
        cursor_year = TODAY.year - rng.randint(0, 2)
        made_current = False
        for k in range(n_pos):
            l1 = main_l1 if k < 2 or rng.random() < 0.7 else rng.choice(job_l1_codes)
            l2 = rng.choice(job_l2_by_parent.get(l1, ["ETC_OTHER"]))
            level = rng.choices(["L1", "L2", "L3", "L4"], weights=[15, 30, 40, 15])[0]
            duration = rng.randint(2, 5)
            end_year = cursor_year
            start_year = max(1975, end_year - duration)
            is_current = not made_current and k == 0
            made_current = made_current or is_current
            # 일부는 의도적으로 10년 초과 이력으로 만들어 경력 필터를 검증할 수 있게 한다
            end_date = None if is_current else date(end_year, rng.randint(1, 12), rng.randint(1, 28))
            session.add(
                Position(
                    person_id=person.person_id,
                    org_name=rng.choice(ORGS_BY_JOB.get(l1, COMPANIES)),
                    title=rng.choice(TITLES_BY_LEVEL[level]),
                    role_level=level,
                    job_l1_code=l1,
                    job_l2_code=l2,
                    is_registered_officer=level in ("L1", "L2") and rng.random() < 0.6,
                    is_full_time=True,
                    start_date=date(start_year, rng.randint(1, 12), rng.randint(1, 28)),
                    end_date=end_date,
                    duties="(더미) 주요 담당 업무",
                    is_current=is_current,
                    # 10년 초과지만 판단에 결정적인 이력 (PRD F-03 (3) 예외)
                    is_highlight=(end_year < TODAY.year - 10 and level == "L1"),
                    source_id=src_a.source_id,
                )
            )
            cursor_year = start_year - rng.randint(0, 2)

        # ---------------- 타사 등기임원 0~3건 (일부는 오버보딩)
        if rng.random() < 0.12:
            n_dir = rng.randint(3, 4)      # 오버보딩 케이스
        elif rng.random() < 0.45:
            n_dir = 0
        else:
            n_dir = rng.randint(1, 2)
        for _ in range(n_dir):
            appointed = _rand_date(rng, TODAY.year - 5, TODAY.year)
            # 일부는 6개월 이내 만료, 일부는 이미 만료(데이터 품질 케이스)
            roll = rng.random()
            if roll < 0.25:
                term_end = TODAY + timedelta(days=rng.randint(10, 180))
            elif roll < 0.85:
                term_end = TODAY + timedelta(days=rng.randint(200, 1000))
            elif roll < 0.95:
                term_end = None                                  # 임기만료일 미상
            else:
                term_end = TODAY - timedelta(days=rng.randint(1, 120))  # 이미 만료
            session.add(
                Directorship(
                    person_id=person.person_id,
                    company_name=rng.choice(COMPANIES),
                    listed_yn=rng.random() < 0.8,
                    role_type=rng.choice(["사외이사", "감사위원", "기타비상무이사"]),
                    appointed_date=appointed,
                    term_end_date=term_end,
                    committee_roles=rng.sample(
                        ["감사위원회", "보상위원회", "사외이사후보추천위원회", "ESG위원회"],
                        k=rng.choice([0, 1, 1, 2]),
                    ),
                    board_attendance_rate=round(rng.uniform(0.55, 1.0), 2),
                    compensation_disclosed=rng.choice([None, 40_000_000, 60_000_000, 80_000_000]),
                    is_current=True,
                    source_id=src_a.source_id,
                )
            )

        # ---------------- 전문분야 1~3개 (근거 스니펫 필수)
        picked = rng.sample(exp_l2_codes, k=rng.randint(1, 3))
        for order, code in enumerate(picked):
            session.add(
                EXP.build(
                    person_id=person.person_id,
                    taxonomy_code=code,
                    evidence_snippet=f"(더미 근거) {code} 관련 경력·저술이 확인됨",
                    source_id=rng.choice([src_a.source_id, src_b.source_id]),
                    level="중",
                    confidence=rng.choice(["상", "중", "하"]),
                    evidence_count=rng.randint(1, 5),
                    is_primary=True,
                )
            )

        # ---------------- 산업 도메인
        for code in rng.sample(industry_codes, k=rng.randint(1, 3)):
            session.add(
                PersonIndustry(
                    person_id=person.person_id, industry_code=code, source_id=src_a.source_id
                )
            )

        # ---------------- 평판 0~3건
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            polarity = rng.choices(["긍정", "중립", "부정"], weights=[45, 35, 20])[0]
            verified = rng.random() < (0.9 if polarity != "부정" else 0.45)
            session.add(
                Reputation(
                    person_id=person.person_id,
                    polarity=polarity,
                    category=rng.choice(["수상·포상", "언론 인터뷰", "법적 분쟁", "규제 제재", "윤리 이슈"]),
                    event_date=_rand_date(rng, TODAY.year - 4, TODAY.year),
                    summary=f"(더미) {polarity} 평판 사례 요약",
                    status=rng.choice(["종결", "진행중", "무혐의", "확정", None]),
                    verified_yn=verified,
                    source_id=src_c.source_id,
                )
            )

        # ---------------- 업적 1~4건
        for _ in range(rng.randint(1, 4)):
            session.add(
                Achievement(
                    person_id=person.person_id,
                    category=rng.choice(["경영 성과", "전문분야 성과", "이사회 기여"]),
                    period=f"{rng.randint(TODAY.year - 12, TODAY.year - 1)}~{rng.randint(TODAY.year - 1, TODAY.year)}",
                    description="(더미) 검증 가능한 성과 기술",
                    quantitative_metric=rng.choice(
                        ["영업이익률 4%→9%", "해외 매출 비중 12%→28%", "내부통제 지적사항 0건", None]
                    ),
                    source_id=rng.choice([src_a.source_id, src_c.source_id]),
                )
            )

        # ---------------- 스크리닝 판정 (2단계 룰엔진 전, 상태 다양성 확보용 더미)
        roll = rng.random()
        if roll < 0.08:
            verdicts = [(rng.choice(["R-01", "R-02", "R-06"]), C.SCREEN_FAIL, "(더미) 결격 가능 사유")]
        elif roll < 0.33:
            verdicts = [(rng.choice(["R-03", "R-04", "R-05"]), C.SCREEN_WARN, "(더미) 확인 필요 사유")]
        else:
            verdicts = [("R-01", C.SCREEN_PASS, None)]
        for rule_id, result, reason in verdicts:
            session.add(
                ScreeningResult(
                    person_id=person.person_id,
                    rule_id=rule_id,
                    result=result,
                    reason=reason,
                )
            )

    return PERSON_COUNT


def _seed_pools(session, rng: random.Random) -> None:
    if session.execute(select(Pool.pool_id).limit(1)).first():
        return
    staff = session.execute(
        select(AppUser).where(AppUser.email == "staff@example.com")
    ).scalar_one_or_none()
    people = list(session.execute(select(Person.person_id).limit(40)).scalars())
    pools = [
        Pool(
            name="2026 감사위원 후보 POOL",
            purpose="임기 만료 예정 감사위원 1인 대체",
            target_position="감사위원",
            target_count=3,
            deadline=TODAY + timedelta(days=90),
            created_by=staff.user_id if staff else None,
        ),
        Pool(
            name="ESG·사이버보안 역량 보완 POOL",
            purpose="이사회 스킬 매트릭스 공백 보완",
            target_position="독립이사",
            target_count=2,
            deadline=TODAY + timedelta(days=150),
            created_by=staff.user_id if staff else None,
        ),
    ]
    session.add_all(pools)
    session.flush()
    for pool in pools:
        for pid in rng.sample(people, k=min(8, len(people))):
            session.add(
                PoolMember(
                    pool_id=pool.pool_id,
                    person_id=pid,
                    state=rng.choice(C.POOL_MEMBER_STATES[:4]),
                    added_by=staff.user_id if staff else None,
                )
            )


def run(reset: bool = False) -> None:
    rng = random.Random(SEED)
    init_db(drop=reset)

    # 코드·설정은 먼저 커밋한다. 인물 시드가 CodeMaster 를 별도 세션으로 조회하므로
    # 같은 트랜잭션 안에 두면 아직 커밋되지 않은 코드를 못 보고 실패한다.
    with session_scope() as s:
        n_codes = CODES.seed_codes(s)
        n_settings = settings.seed_defaults(s)

    with session_scope() as s:
        _seed_users(s)

    with session_scope() as s:
        n_people = _seed_people(s, rng)

    with session_scope() as s:
        _seed_pools(s, rng)

    print("=" * 60)
    print("더미데이터 생성 완료 (합성 데이터 — 실존 인물 아님)")
    print(f"  CodeMaster : {n_codes}건 추가")
    print(f"  AppSetting : {n_settings}건 추가")
    print(f"  Person     : {n_people}명 추가")
    print("=" * 60)
    print("로그인 계정 (모의 로그인):")
    print("  staff@example.com / head@example.com / legal@example.com")
    print("  admin@example.com / viewer@example.com / viewer-expired@example.com")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="합성 더미데이터 생성")
    parser.add_argument("--reset", action="store_true", help="기존 테이블 삭제 후 재생성")
    args = parser.parse_args()
    if args.reset:
        answer = input("모든 데이터를 삭제하고 재생성합니다. 계속할까요? [y/N] ").strip().lower()
        if answer != "y":
            print("취소했습니다.")
            sys.exit(0)
    run(reset=args.reset)
