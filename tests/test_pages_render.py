"""데이터가 있는 상태에서 각 페이지가 실제로 렌더링되는지 검증한다.

빈 DB 만으로 테스트하면 페이지가 조기 st.stop() 해서 렌더링 버그를 놓친다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import constants as C
from core.auth import CurrentUser
from core.state import K_LAST_ACTIVE, K_USER

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PAGES_WITH_TABLE = [
    "pages/0_대시보드.py",
    "pages/1_후보_검색.py",
    "pages/4_POOL_관리.py",
    "pages/7_관리자.py",
]
ALL_PAGES = PAGES_WITH_TABLE + [
    "pages/2_후보_상세.py",
    "pages/3_후보_비교.py",
    "pages/5_검수.py",
    "pages/6_리포트.py",
    "pages/8_공유_관리.py",
]


def _run(path: str, role: str = C.ROLE_ADMIN):
    at = AppTest.from_file(str(PROJECT_ROOT / path), default_timeout=60)
    at.session_state[K_USER] = CurrentUser(
        user_id=1, email="admin@example.com", display_name="가상 관리자", role=role
    )
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    return at.run()


# 데이터에 따라 의도적으로 st.error 로 표시하는 도메인 경고.
# 이것들은 렌더링 오류가 아니므로 허용한다. (출처 누락 F-05-1 등은 허용하지 않는다)
EXPECTED_DOMAIN_ALERTS = ("(PRD F-03-2)", "(PRD F-08-1)")


@pytest.mark.parametrize("path", ALL_PAGES)
def test_page_renders_without_exception(path):
    at = _run(path)
    assert not at.exception, f"{path}: {at.exception}"
    unexpected = [
        e.value for e in at.error if not any(tag in e.value for tag in EXPECTED_DOMAIN_ALERTS)
    ]
    assert not unexpected, f"{path} 에 오류 메시지가 표시됨: {unexpected}"


@pytest.mark.parametrize("path", PAGES_WITH_TABLE)
def test_page_shows_data(path):
    at = _run(path)
    assert len(at.dataframe) > 0, f"{path} 가 데이터를 표시하지 않음"


def test_search_page_has_no_text_input():
    """검색은 드롭다운 전용이다. 키워드 입력창이 있으면 원칙 위반 (불변규칙 3).

    예외는 검색 조건이 아닌 입력뿐이다: 프리셋 이름, POOL 저장 정보(명칭·목적·대상 직위·메모).
    """
    at = _run("pages/1_후보_검색.py")
    non_search_keys = {"preset_name", "pool_memo", "pool_name", "pool_purpose", "pool_target"}
    others = [t for t in at.text_input if t.key not in non_search_keys]
    assert not others, f"후보 검색 화면에 검색용 텍스트 입력창이 존재함: {[t.key for t in others]}"
    assert len(at.selectbox) > 0
    assert len(at.multiselect) > 0


def test_search_page_reports_truncation():
    """결과가 잘렸을 때 '전체 매칭 N명 중 상위 M명' 이 표기되는지 (PRD F-01-8)."""
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/1_후보_검색.py"), default_timeout=60)
    at.session_state[K_USER] = CurrentUser(
        user_id=1, email="staff@example.com", display_name="가상 담당자", role=C.ROLE_STAFF
    )
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    at.session_state["search.result_limit_code"] = "N10"
    at.run()
    assert not at.exception
    banners = [w.value for w in at.warning] + [s.value for s in at.success]
    assert any("전체 매칭" in b for b in banners), f"절단 안내가 없음: {banners}"


def test_detail_page_shows_source_for_every_fact():
    """상세 화면에 출처 없는 값 경고가 뜨지 않아야 한다 (PRD F-05-1)."""
    at = _run("pages/2_후보_상세.py")
    assert not at.exception
    assert not any("출처 정보가 없습니다" in e.value for e in at.error)


def test_report_page_blocks_unreviewed_export():
    """검수 미완료 프로파일은 출력이 차단된다 (PRD F-08-1)."""
    at = _run("pages/6_리포트.py")
    assert not at.exception
    messages = [e.value for e in at.error] + [s.value for s in at.success]
    assert messages, "출력 가능 여부가 표시되지 않음"
    blocked = any("F-08-1" in e.value for e in at.error)
    if blocked:
        # 차단 시 개인 PDF 생성 버튼은 비활성이어야 한다
        buttons = [b for b in at.button if "사추위 보고용 PDF" in b.label]
        assert buttons and all(b.disabled for b in buttons)


def test_report_page_blocks_unreviewed_person():
    """미검수 후보를 고르면 PDF 생성 버튼이 비활성이다 (인수 기준 #8)."""
    from sqlalchemy import select

    from data.models import Person
    from data.session import session_scope

    with session_scope() as s:
        pid = s.execute(select(Person.person_id).where(Person.profile_status == C.PROFILE_UNREVIEWED)).scalars().first()
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/6_리포트.py"), default_timeout=60)
    at.session_state[K_USER] = CurrentUser(user_id=1, email="staff@example.com", display_name="가상 담당자",
                                           role=C.ROLE_STAFF)
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    at.run()
    at.selectbox(key="report_person").set_value(pid).run()
    assert not at.exception
    assert any("F-08-1" in e.value for e in at.error)
    buttons = [b for b in at.button if "사추위 보고용 PDF" in b.label]
    assert buttons and all(b.disabled for b in buttons)
