"""관리자 화면 — 코드·설정 CRUD (PRD F-01-7, 불변규칙 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import codes as CODES
from core import constants as C
from core import settings
from core.audit import history_of
from core.state import K_LAST_ACTIVE, K_USER
from data.models import CodeMaster
from tests.helpers import user_for

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_admin():
    at = AppTest.from_file(str(PROJECT_ROOT / "pages/7_관리자.py"), default_timeout=60)
    at.session_state[K_USER] = user_for(C.ROLE_ADMIN)
    at.session_state[K_LAST_ACTIVE] = datetime.now(timezone.utc)
    return at.run()


# ------------------------------------------------------------------ core/codes.py CRUD


def test_create_code_then_duplicate_rejected():
    CODES.create_code(C.CODE_REGION, "TEST_RG_A", "테스트지역A")
    with pytest.raises(ValueError):
        CODES.create_code(C.CODE_REGION, "TEST_RG_A", "다른 표시명")
    labels = {r.code: r.label for r in CODES.load_all(C.CODE_REGION)}
    assert labels["TEST_RG_A"] == "테스트지역A"


def test_create_code_requires_label():
    with pytest.raises(ValueError):
        CODES.create_code(C.CODE_REGION, "TEST_RG_B", "   ")


def test_update_code_changes_label_order_active_and_logs_audit():
    CODES.create_code(C.CODE_REGION, "TEST_RG_C", "원래표시명", sort_order=1)
    row = next(r for r in CODES.load_all(C.CODE_REGION) if r.code == "TEST_RG_C")

    before = len(history_of("code", prefix=f"{C.CODE_REGION}/TEST_RG_C"))
    CODES.update_code(row.id, label="새표시명", sort_order=9, is_active=False, user_id=None)

    updated = next(r for r in CODES.load_all(C.CODE_REGION) if r.code == "TEST_RG_C")
    assert updated.label == "새표시명"
    assert updated.sort_order == 9
    assert updated.is_active is False
    assert len(history_of("code", prefix=f"{C.CODE_REGION}/TEST_RG_C")) == before + 1

    # 비활성화된 코드는 load_codes(활성만)에서 빠지고 load_all(전체)에는 남는다
    assert "TEST_RG_C" not in {r.code for r in CODES.load_codes(C.CODE_REGION)}
    assert "TEST_RG_C" in {r.code for r in CODES.load_all(C.CODE_REGION)}


def test_update_code_noop_does_not_add_audit_entry():
    CODES.create_code(C.CODE_REGION, "TEST_RG_D", "동일값유지")
    row = next(r for r in CODES.load_all(C.CODE_REGION) if r.code == "TEST_RG_D")
    before = len(history_of("code", prefix=f"{C.CODE_REGION}/TEST_RG_D"))
    CODES.update_code(row.id, label="동일값유지", sort_order=row.sort_order, is_active=True)
    assert len(history_of("code", prefix=f"{C.CODE_REGION}/TEST_RG_D")) == before


def test_update_code_missing_row_raises():
    with pytest.raises(LookupError):
        CODES.update_code(999_999, label="x")


# ------------------------------------------------------------------ core/settings.py + 감사이력


def test_settings_list_all_includes_metadata():
    items = settings.list_all()
    assert any(it.key == C.SET_COOLING_OFF_YEARS for it in items)
    row = next(it for it in items if it.key == C.SET_COOLING_OFF_YEARS)
    assert row.legal_basis  # 법령 근거가 있는 항목이다


def test_setting_update_via_set_value_then_manual_audit_log():
    from core.audit import log_change

    key = C.SET_COOLING_OFF_YEARS
    before_val = settings.get_str(key)
    try:
        before_hist = len(history_of("setting", prefix=key))
        before = settings.set_value(key, "4")
        log_change(None, "setting", "update", key, f"{before} → 4")
        assert settings.get_int(key) == 4
        assert len(history_of("setting", prefix=key)) == before_hist + 1
    finally:
        settings.set_value(key, before_val)


# ------------------------------------------------------------------ 페이지 상호작용


def test_admin_page_renders_and_lists_categories():
    at = _run_admin()
    assert not at.exception
    assert len(at.selectbox(key="admin_code_category").options) > 0


def test_admin_page_add_code_via_form():
    at = _run_admin()
    at.selectbox(key="admin_code_category").set_value(C.CODE_REGION).run()
    assert not at.exception

    at.text_input(key="admin_code_new_code").set_value("PAGE_TEST_CODE").run()
    at.text_input(key="admin_code_new_label").set_value("페이지테스트표시명").run()

    submit = next(b for b in at.button if b.key and "admin_code_add_form" in b.key)
    at = submit.click().run()
    assert not at.exception

    codes = {r.code for r in CODES.load_all(C.CODE_REGION)}
    assert "PAGE_TEST_CODE" in codes


def test_admin_page_edit_setting_via_form():
    at = _run_admin()
    at.tabs[1]  # 운영 파라미터 탭 존재 확인
    key = C.SET_TERM_ALERT_MONTHS
    before_val = settings.get_str(key)
    try:
        at.selectbox(key="admin_setting_key").set_value(key).run()
        at.text_input(key="admin_setting_value").set_value("9").run()
        save_btn = next(b for b in at.button if "저장" in (b.label or "") and b.key and "admin_setting_edit_form" in b.key)
        at = save_btn.click().run()
        assert not at.exception
        assert settings.get_int(key) == 9
    finally:
        settings.set_value(key, before_val)
