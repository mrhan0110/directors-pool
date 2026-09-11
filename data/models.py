"""SQLAlchemy 모델 (PRD §7 논리 스키마).

설계 원칙
- 사실 데이터 테이블(Position / Directorship / Expertise / Reputation / Achievement)은
  source_id 를 NOT NULL 외래키로 둔다. 출처 없는 값은 DB 레벨에서 저장 불가.
  (PRD F-05-1, 불변규칙 1)
- Expertise 는 근거 스니펫(evidence_snippet)도 NOT NULL 이다.
  근거 없는 분류가 새어나오는 경로를 스키마에서 차단한다. (PRD F-04-2, 불변규칙 2)
- Directorship.remaining_term_months 는 저장 컬럼이 아니라 계산 프로퍼티다.
  (PRD 1단계 지시 2, F-03-1)
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.constants import PROFILE_UNREVIEWED


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ===================================================================== 출처

class Source(Base):
    """모든 사실 데이터가 참조하는 출처 (PRD F-05-1)."""

    __tablename__ = "source"

    source_id: Mapped[int] = mapped_column(primary_key=True)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_tier: Mapped[str] = mapped_column(String(1), nullable=False)  # A / B / C
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    snapshot_path: Mapped[str | None] = mapped_column(String(500))
    quote_snippet: Mapped[str | None] = mapped_column(Text)
    url_alive_yn: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_source_tier", "source_tier"),)

    def citation(self) -> str:
        """PRD 부록 B 출처 표기 표준 형식."""
        pub = self.published_date.isoformat() if self.published_date else "발행일 미상"
        collected = self.collected_at.date().isoformat() if self.collected_at else "-"
        return f"[출처] {self.publisher}, 「{self.doc_title}」, {pub}, {self.url} (수집일 {collected})"


# ===================================================================== 인물

class Person(Base):
    __tablename__ = "person"

    person_id: Mapped[int] = mapped_column(primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200))
    gender: Mapped[str | None] = mapped_column(String(10))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    # 출생연도만 공개된 경우 만 나이는 추정치다 (PRD §6.2 '만 OO세(추정)')
    age_estimated_yn: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    nationality: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # JSON 컬럼은 DB 종류마다 질의 문법이 달라 검색 필터로 쓰기 어렵다.
    # 필터용으로 대표 국적을 비정규화해 둔다 (표시는 nationality 리스트를 쓴다).
    nationality_primary: Mapped[str | None] = mapped_column(String(10))
    multi_nationality_yn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    residence_region: Mapped[str | None] = mapped_column(String(50))
    education: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    certifications: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    profile_status: Mapped[str] = mapped_column(
        String(20), default=PROFILE_UNREVIEWED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    # 보관기간 경과 시 자동 파기 대상 (PRD §5.2)
    retention_until: Mapped[date | None] = mapped_column(Date)

    positions: Mapped[list["Position"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    directorships: Mapped[list["Directorship"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    expertises: Mapped[list["Expertise"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    reputations: Mapped[list["Reputation"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["Achievement"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    screenings: Mapped[list["ScreeningResult"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_person_name", "name_ko"),
        Index("ix_person_birth", "birth_year"),
        Index("ix_person_gender", "gender"),
    )

    def age(self, today: date | None = None) -> int | None:
        """만 나이. 출생연도만 있으므로 연도 차이로 근사한다."""
        if self.birth_year is None:
            return None
        today = today or date.today()
        return today.year - self.birth_year


class Position(Base):
    """경력. 현직·과거직 모두 포함한다 (PRD §7)."""

    __tablename__ = "position"

    position_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    org_name: Mapped[str] = mapped_column(String(300), nullable=False)
    org_id: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # 임원급 판정에 쓰이는 등급. 최근 10년 + 임원급 필터의 기준 (PRD F-03 (3))
    role_level: Mapped[str | None] = mapped_column(String(50))
    # 직업 대/중분류 코드 (CodeMaster JOB_L1 / JOB_L2). 검색 필터의 기준 (PRD F-01)
    job_l1_code: Mapped[str | None] = mapped_column(String(50))
    job_l2_code: Mapped[str | None] = mapped_column(String(50))
    is_registered_officer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_full_time: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    term_end_date: Mapped[date | None] = mapped_column(Date)
    duties: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 10년 초과 이력이라도 판단에 결정적인 경우 하이라이트로 노출 (PRD F-03 (3))
    is_highlight: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 검수자가 수정한 항목은 자동 갱신이 덮어쓰지 않는다 (PRD F-08-4)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)

    person: Mapped[Person] = relationship(back_populates="positions")
    source: Mapped[Source] = relationship()

    __table_args__ = (
        Index("ix_position_person", "person_id"),
        Index("ix_position_current", "is_current"),
        Index("ix_position_job", "job_l1_code", "job_l2_code"),
    )


class PersonIndustry(Base):
    """산업 도메인 경험 (PRD §6.1 '산업 도메인 경험' 필터).

    경력에서 도출되는 사실이므로 근거 출처를 함께 둔다.
    """

    __tablename__ = "person_industry"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    industry_code: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("person_id", "industry_code", name="uq_person_industry"),
        Index("ix_person_industry_code", "industry_code"),
    )


class Directorship(Base):
    """타사 등기임원 수행 현황 (PRD F-03 (4)). Position 의 특수 뷰 성격."""

    __tablename__ = "directorship"

    directorship_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(50))
    listed_yn: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_type: Mapped[str] = mapped_column(String(50), nullable=False)
    appointed_date: Mapped[date | None] = mapped_column(Date)
    term_end_date: Mapped[date | None] = mapped_column(Date)
    committee_roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    board_attendance_rate: Mapped[float | None] = mapped_column(Float)
    compensation_disclosed: Mapped[int | None] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)

    person: Mapped[Person] = relationship(back_populates="directorships")
    source: Mapped[Source] = relationship()

    __table_args__ = (Index("ix_directorship_person", "person_id"),)

    def remaining_term_months(self, today: date | None = None) -> int | None:
        """잔여 임기(개월). 저장 컬럼이 아닌 계산값이다 (PRD F-03-1).

        - 임기만료일 미상이면 None
        - 이미 만료된 건은 음수를 반환한다. 호출부에서 '만료'로 표기한다.
        """
        if self.term_end_date is None:
            return None
        today = today or date.today()
        months = (self.term_end_date.year - today.year) * 12 + (
            self.term_end_date.month - today.month
        )
        if self.term_end_date.day < today.day:
            months -= 1
        return months


class Expertise(Base):
    """전문분야 (PRD F-04).

    evidence_snippet 이 NOT NULL 이라는 점이 핵심이다.
    근거 없는 분류를 스키마에서 차단한다 (불변규칙 2).
    """

    __tablename__ = "expertise"

    expertise_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    taxonomy_code: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)  # 대 / 중
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # 상 / 중 / 하
    evidence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    evidence_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_by_user_yn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 분류 가중 점수 (PRD §6.4 분류 로직 3). 대표/보조 판정의 근거
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)
    extra_source_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    person: Mapped[Person] = relationship(back_populates="expertises")
    source: Mapped[Source] = relationship()

    __table_args__ = (
        UniqueConstraint("person_id", "taxonomy_code", name="uq_expertise_person_code"),
        Index("ix_expertise_code", "taxonomy_code"),
    )


class Reputation(Base):
    """평판 (PRD F-03 (5)). 미확인 건은 verified_yn=False 로 구분하고 점수에 반영하지 않는다."""

    __tablename__ = "reputation"

    reputation_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    polarity: Mapped[str] = mapped_column(String(10), nullable=False)  # 긍정 / 중립 / 부정
    category: Mapped[str | None] = mapped_column(String(50))
    event_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(20))  # 진행중 / 종결 / 무혐의 / 확정
    verified_yn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)

    person: Mapped[Person] = relationship(back_populates="reputations")
    source: Mapped[Source] = relationship()

    __table_args__ = (Index("ix_reputation_person", "person_id"),)


class Achievement(Base):
    __tablename__ = "achievement"

    achievement_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    period: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantitative_metric: Mapped[str | None] = mapped_column(String(300))
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)

    person: Mapped[Person] = relationship(back_populates="achievements")
    source: Mapped[Source] = relationship()

    __table_args__ = (Index("ix_achievement_person", "person_id"),)


class ScreeningResult(Base):
    """결격·리스크 스크리닝 결과 (PRD §5.1). 판정 로직은 2단계."""

    __tablename__ = "screening_result"

    screening_id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(10), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)  # pass / warn / fail
    reason: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reviewer_override: Mapped[str | None] = mapped_column(String(10))
    override_reason: Mapped[str | None] = mapped_column(Text)

    person: Mapped[Person] = relationship(back_populates="screenings")

    __table_args__ = (
        UniqueConstraint("person_id", "rule_id", name="uq_screening_person_rule"),
        Index("ix_screening_result", "result"),
    )


# ===================================================================== POOL

class Pool(Base):
    __tablename__ = "pool"

    pool_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    target_position: Mapped[str | None] = mapped_column(String(100))
    target_count: Mapped[int | None] = mapped_column(Integer)
    deadline: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    members: Mapped[list["PoolMember"]] = relationship(
        back_populates="pool", cascade="all, delete-orphan"
    )


class PoolMember(Base):
    __tablename__ = "pool_member"

    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("pool.pool_id"), nullable=False)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="후보 등록", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    # 제외·보류 시 사유 필수 (PRD F-07)
    reason: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    pool: Mapped[Pool] = relationship(back_populates="members")
    person: Mapped[Person] = relationship()

    __table_args__ = (UniqueConstraint("pool_id", "person_id", name="uq_pool_person"),)


# ===================================================================== 검수 / 감사

class ReviewLog(Base):
    """검수 이력 (PRD F-08-3). 수동 수정 항목은 자동 갱신이 덮어쓰지 않는다(F-08-4)."""

    __tablename__ = "review_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    field_path: Mapped[str] = mapped_column(String(200), nullable=False)
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 승인 / 수정 / 삭제
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    """데이터 변경 감사로그. 열람 로그는 AccessLog 로 분리 운영한다."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AccessLog(Base):
    """접근 로그 (PRD F-09-22). Streamlit 기본 로그로는 감사 요건을 못 채운다."""

    __tablename__ = "access_log"

    log_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    share_id: Mapped[int | None] = mapped_column(ForeignKey("share_link.share_id"))
    page: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    target_person_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_accesslog_time", "occurred_at"),)


# ===================================================================== 사용자 / 공유

class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    org_affiliation: Mapped[str | None] = mapped_column(String(200))
    idp_subject: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 외부뷰어는 접근 만료일이 필수다 (PRD F-09-12)
    expires_at: Mapped[date | None] = mapped_column(Date)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class ShareLink(Base):
    """공유 링크 (PRD F-09-14~16). 토큰은 해시로만 저장하고 원문은 보관하지 않는다."""

    __tablename__ = "share_link"

    share_id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("pool.pool_id"), nullable=False)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    recipient_email: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="read_only", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ===================================================================== 코드 / 설정

class CodeMaster(Base):
    """드롭다운 코드 (PRD F-01-7). 모든 검색 선택지는 여기서 로드한다."""

    __tablename__ = "code_master"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("category", "code", name="uq_code_category_code"),
        Index("ix_code_category", "category", "parent_code"),
    )


class AppSetting(Base):
    """운영 파라미터 (불변규칙 4).

    법령 연동 임계값을 코드에 박지 않기 위한 테이블이다.
    관리자 화면에서 수정하며 변경 이력은 AuditLog 에 남긴다.
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    value_type: Mapped[str] = mapped_column(String(10), default="int", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 법령 근거를 함께 적어 둔다. 개정 시 무엇을 확인해야 하는지 추적하기 위함
    legal_basis: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))


class PersonScore(Base):
    """적합도 기본 점수 (PRD F-06).

    검색 조건과 무관한 부분(스킬갭·경력·가용성·리스크)만 저장한다.
    전문분야 매칭도는 검색 조건에 따라 달라지므로 검색 시 SQL 로 더한다.
    """

    __tablename__ = "person_score"

    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), primary_key=True)
    base_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SearchPreset(Base):
    """검색 프리셋 (PRD F-01-5). 조회 인원 수도 함께 저장한다 (F-01-8)."""

    __tablename__ = "search_preset"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limit_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_preset_user_name"),)


class UserPreference(Base):
    """사용자별 최근 선택값 (PRD F-01-8 '사용자별 최근 선택값 기억')."""

    __tablename__ = "user_preference"

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class ConsiderationCheck(Base):
    """선정 고려사항 18개 항목의 수기 확인·코멘트·첨부 (PRD F-03 (7), F-03-5)."""

    __tablename__ = "consideration_check"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str | None] = mapped_column(String(20))  # 확인 필요 / 이상 없음 / 우려 있음
    comment: Mapped[str | None] = mapped_column(Text)
    attachment_name: Mapped[str | None] = mapped_column(String(300))
    attachment: Mapped[bytes | None] = mapped_column(LargeBinary)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("person_id", "item_no", name="uq_consideration_item"),)


class FieldConflict(Base):
    """출처 간 상충 정보 (PRD F-05-3).

    상위 등급 값을 채택하고, 하위 등급 값을 '대체 정보'로 병기해 충돌 사실을 숨기지 않는다.
    대체 정보도 출처가 있어야 한다 (불변규칙 1).
    """

    __tablename__ = "field_conflict"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(50), nullable=False)  # position / directorship / person
    entity_id: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    adopted_value: Mapped[str | None] = mapped_column(Text)
    adopted_source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)
    alt_value: Mapped[str | None] = mapped_column(Text)
    alt_source_id: Mapped[int] = mapped_column(ForeignKey("source.source_id"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_conflict_person", "person_id"),)


class ExpertiseHistory(Base):
    """전문분야 수정·확정 이력 (PRD F-04-4, 모델 개선 피드백 루프)."""

    __tablename__ = "expertise_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    taxonomy_code: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 확정 / 대표지정 / 보조지정 / 삭제
    before_value: Mapped[str | None] = mapped_column(Text)
    after_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class PoolEvent(Base):
    """POOL 변경 이력 및 담당자 코멘트 타임라인 (PRD F-07)."""

    __tablename__ = "pool_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("pool.pool_id"), nullable=False)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.person_id"))
    event: Mapped[str] = mapped_column(String(30), nullable=False)  # 추가 / 상태변경 / 코멘트 / 제외
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ix_pool_event_pool", "pool_id"),)


class PersonBlocklist(Base):
    """삭제 요청 후보의 재수집 차단 목록 (PRD §5.2).

    개인정보 최소화를 위해 이름 원문 대신 해시만 저장한다.
    """

    __tablename__ = "person_blocklist"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ReviewQueue(Base):
    """자동 결합 신뢰도가 낮은 동명이인 후보 등을 수기 확인으로 보내는 큐 (PRD §11)."""

    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="대기", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
