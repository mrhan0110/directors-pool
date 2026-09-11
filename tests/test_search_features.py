"""검색 부가 기능 테스트 (PRD F-01-3·5·6·8, F-02-5)."""

from __future__ import annotations

import pytest

from core import constants as C
from core import preferences, presets, search, settings


@pytest.fixture
def page_size_10():
    before = settings.get_raw(C.SET_PAGE_SIZE)
    settings.set_value(C.SET_PAGE_SIZE, "10")
    yield
    settings.set_value(C.SET_PAGE_SIZE, before)


# ------------------------------------------------------------------ 페이지네이션 (F-02-5)

def test_pages_cover_top_n_exactly_once(page_size_10):
    f = {"sort": "FIT"}
    first = search.search(f, "N20", C.ROLE_STAFF, page=1)
    second = search.search(f, "N20", C.ROLE_STAFF, page=2)
    assert first.shown == 20 and first.page_count == 2
    ids = [r.person_id for r in first.rows] + [r.person_id for r in second.rows]
    assert len(ids) == 20 and len(set(ids)) == 20
    assert ids == search.search_ids(f, "N20", C.ROLE_STAFF)


def test_last_page_is_partial_and_never_exceeds_n(page_size_10):
    total = search.count_matches({})
    r = search.search({}, "NALL", C.ROLE_STAFF, page=99)  # 범위 밖 → 마지막 페이지로
    assert r.page == r.page_count
    assert len(r.rows) == total - (r.page_count - 1) * 10


def test_page_size_and_limit_are_independent(page_size_10):
    r = search.search({}, "N10", C.ROLE_STAFF, page=1)
    assert r.page_count == 1 and len(r.rows) == 10


# ------------------------------------------------------------------ 건수 배지·완화 제안

def test_option_counts_match_individual_searches():
    counts = search.option_counts({}, C.CODE_GENDER, "gender")
    for code, n in counts.items():
        assert n == search.count_matches({"gender": code})
    # 성별 미상 후보는 어느 항목에도 잡히지 않는다
    assert sum(counts.values()) <= search.count_matches({})


def test_option_counts_respect_other_filters():
    base = {"nationalities": ["KR"]}
    counts = search.option_counts(base, C.CODE_GENDER, "gender")
    assert counts["F"] == search.count_matches({**base, "gender": "F"})


def test_relaxation_suggests_removing_impossible_filter():
    f = {"nationalities": ["CN"], "gender": "F"}
    assert search.count_matches(f) == 0
    labels = [label for label, _ in search.relaxation_suggestions(f)]
    assert "국적" in labels


# ------------------------------------------------------------------ 프리셋 (F-01-5)

def test_preset_roundtrip_and_upsert():
    pid = presets.save_preset(1, "감사위원 후보 – 여성", {"gender": "F"}, "N50")
    again = presets.save_preset(1, "감사위원 후보 – 여성", {"gender": "F", "age_bands": ["A55"]}, "N20")
    assert pid == again
    p = presets.get_preset(1, pid)
    assert p.filters["age_bands"] == ["A55"] and p.limit_code == "N20"
    assert any(x.id == pid for x in presets.list_presets(1))
    assert presets.delete_preset(1, pid) is True


def test_preset_is_private_to_owner():
    pid = presets.save_preset(1, "내 프리셋", {}, None)
    assert presets.get_preset(2, pid) is None
    assert presets.delete_preset(2, pid) is False
    assert presets.get_preset(1, pid) is not None
    presets.delete_preset(1, pid)


def test_preset_requires_name():
    with pytest.raises(ValueError):
        presets.save_preset(1, "   ", {}, None)


# ------------------------------------------------------------------ 최근 선택값 (F-01-8)

def test_limit_preference_is_remembered_per_user():
    assert preferences.get_pref(3, "test.key") is None
    preferences.set_pref(3, "test.key", "N100")
    preferences.set_pref(3, "test.key", "N50")
    assert preferences.get_pref(3, "test.key") == "N50"
    assert preferences.get_pref(4, "test.key") is None
