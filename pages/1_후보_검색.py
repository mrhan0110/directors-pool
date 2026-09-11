"""S-02 후보 검색 (PRD F-01, F-02).

모든 검색 조건은 드롭다운이다. 키워드 입력창을 만들지 않는다. (불변규칙 3, F-09-1)
화면의 유일한 텍스트 입력은 '프리셋 이름'이며, 검색 조건으로는 절대 쓰이지 않는다.
검색·집계 로직은 core/search.py 에 있고 이 파일은 표현만 담당한다.
"""

from __future__ import annotations

import json

import streamlit as st

from core import codes as CODES
from core import constants as C
from core import preferences, presets, scoring, search, settings, state
from core.audit import log_access
from core.guard import confidential_notice, require, stage_notice

user = require("search")

st.title("후보 검색")
confidential_notice()

f = state.filters()

SINGLE_FILTERS = [
    ("gender", "성별", C.CODE_GENDER),
    ("concurrent", "겸직 수", C.CODE_CONCURRENT),
    ("term_remain", "잔여임기", C.CODE_TERM_REMAIN),
    ("screening", "스크리닝", C.CODE_SCREENING),
    ("reputation", "평판", C.CODE_REPUTATION),
    ("freshness", "최신성", C.CODE_FRESHNESS),
]
MULTI_FILTERS = [
    ("age_bands", "연령", C.CODE_AGE_BAND),
    ("job_l1", "직업", C.CODE_JOB_L1),
    ("job_l2", "직업(중)", C.CODE_JOB_L2),
    ("role_levels", "직급", C.CODE_ROLE_LEVEL),
    ("expertise_l1", "전문분야", C.CODE_EXPERTISE_L1),
    ("expertise_l2", "전문분야(중)", C.CODE_EXPERTISE_L2),
    ("industries", "산업", C.CODE_INDUSTRY),
    ("nationalities", "국적", C.CODE_NATIONALITY),
    ("regions", "지역", C.CODE_REGION),
]
CHILD_OF = {"job_l1": "job_l2", "expertise_l1": "expertise_l2"}
WIDGET_PREFIXES = ("sel_", "multi_", "radio_")


@st.cache_data(ttl=60, show_spinner=False)
def _option_counts(filters_json: str, category: str, filter_key: str) -> dict[str, int]:
    """항목별 후보 수 배지 (F-01-3).

    역할과 무관한 공용 집계이고 외부뷰어는 이 화면에 들어올 수 없으므로 사용자 ID 없이 캐시한다 (F-09-7).
    """
    return search.option_counts(json.loads(filters_json), category, filter_key)


def _filters_json() -> str:
    return json.dumps(f, sort_keys=True, ensure_ascii=False, default=str)


def _reset_widgets() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(WIDGET_PREFIXES) or key in ("w_sort", "w_limit", "w_page"):
            st.session_state.pop(key, None)


def _select(label: str, category: str, filter_key: str) -> None:
    """단일 선택. '전체'가 기본값이며 미선택 시 조건에서 제외한다 (F-01-1)."""
    items = CODES.load_codes(category)
    counts = _option_counts(_filters_json(), category, filter_key)
    options = [CODES.ALL] + [i.code for i in items]
    labels = {CODES.ALL: CODES.ALL_LABEL, **{i.code: f"{i.label} ({counts.get(i.code, 0)})" for i in items}}
    current = f.get(filter_key) or CODES.ALL
    picked = st.selectbox(
        label,
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda c: labels.get(c, c),
        key=f"sel_{filter_key}",
    )
    state.set_filter(filter_key, None if picked == CODES.ALL else picked)


def _multi(
    label: str,
    category: str,
    filter_key: str,
    parent_codes: list[str] | None = None,
    max_selections: int | None = None,
) -> None:
    if parent_codes:
        items = [i for code in parent_codes for i in CODES.load_codes(category, parent_code=code)]
    else:
        items = CODES.load_codes(category)
    counts = _option_counts(_filters_json(), category, filter_key)
    options = [i.code for i in items]
    labels = {i.code: f"{i.label} ({counts.get(i.code, 0)})" for i in items}
    current = [c for c in (f.get(filter_key) or []) if c in options]
    picked = st.multiselect(
        label,
        options,
        default=current,
        format_func=lambda c: labels.get(c, c),
        key=f"multi_{filter_key}",
        max_selections=max_selections,
        placeholder="전체",
    )
    state.set_filter(filter_key, picked)


def _cascade(parent_key: str, prev: list) -> None:
    """상위 선택이 바뀌면 하위 선택을 초기화한다 (F-01-2, F-09-3)."""
    if list(f.get(parent_key) or []) != prev:
        state.clear_dependent(parent_key)
        st.session_state.pop(f"multi_{CHILD_OF[parent_key]}", None)


def _remove_chip(key: str, value) -> None:
    """조건 칩 개별 해제 (F-01-4)."""
    cur = state.filters().get(key)
    if isinstance(cur, list):
        state.set_filter(key, [v for v in cur if v != value])
    elif key == "job_scope":
        state.set_filter(key, "BOTH")
    else:
        state.set_filter(key, None)
    for prefix in WIDGET_PREFIXES:
        st.session_state.pop(f"{prefix}{key}", None)
    if key in CHILD_OF:
        state.clear_dependent(key)
        st.session_state.pop(f"multi_{CHILD_OF[key]}", None)


def _apply_preset(p: presets.Preset) -> None:
    restored = dict(state.DEFAULT_FILTERS)
    restored.update({k: v for k, v in p.filters.items() if k in state.DEFAULT_FILTERS})
    state.put(state.K_FILTERS, restored)
    if p.limit_code:
        state.put(state.K_RESULT_LIMIT, p.limit_code)
    _reset_widgets()


# ------------------------------------------------------------------ 필터 패널

with st.sidebar:
    st.subheader("검색 조건")
    st.caption("모든 조건은 선택식입니다. 괄호 안 숫자는 다른 조건을 유지했을 때의 후보 수입니다.")

    _select("성별", C.CODE_GENDER, "gender")
    _multi("연령", C.CODE_AGE_BAND, "age_bands")

    st.markdown("**직업**")
    scope_items = CODES.load_codes(C.CODE_JOB_SCOPE)
    scope_options = [i.code for i in scope_items]
    scope_labels = {i.code: i.label for i in scope_items}
    scope_current = f.get("job_scope") or "BOTH"
    scope = st.radio(
        "직업 구분",
        scope_options,
        index=scope_options.index(scope_current) if scope_current in scope_options else 0,
        format_func=lambda c: scope_labels[c],
        key="radio_job_scope",
    )
    state.set_filter("job_scope", scope)

    prev_l1 = list(f.get("job_l1") or [])
    _multi("직업 — 대분류", C.CODE_JOB_L1, "job_l1")
    _cascade("job_l1", prev_l1)
    if f.get("job_l1"):
        _multi("직업 — 중분류", C.CODE_JOB_L2, "job_l2", parent_codes=list(f["job_l1"]))
    _multi("직급 수준", C.CODE_ROLE_LEVEL, "role_levels")

    st.markdown("**전문분야**")
    prev_exp1 = list(f.get("expertise_l1") or [])
    _multi("전문분야 — 대분류", C.CODE_EXPERTISE_L1, "expertise_l1")
    _cascade("expertise_l1", prev_exp1)
    if f.get("expertise_l1"):
        _multi(
            "전문분야 — 중분류 (최대 3개)",
            C.CODE_EXPERTISE_L2,
            "expertise_l2",
            parent_codes=list(f["expertise_l1"]),
            max_selections=3,
        )

    _multi("산업 도메인 경험", C.CODE_INDUSTRY, "industries")
    _multi("국적", C.CODE_NATIONALITY, "nationalities")
    _select("현 타사 등기임원 겸직 수", C.CODE_CONCURRENT, "concurrent")
    _select("겸직 잔여임기", C.CODE_TERM_REMAIN, "term_remain")
    _select("결격사유 스크리닝", C.CODE_SCREENING, "screening")
    _select("부정 평판 이슈", C.CODE_REPUTATION, "reputation")
    _multi("거주·활동 지역", C.CODE_REGION, "regions")
    _select("데이터 최신성", C.CODE_FRESHNESS, "freshness")

    st.divider()
    if st.button("조건 초기화", width="stretch"):
        state.reset_filters()
        _reset_widgets()
        st.rerun()

    # ---------------- 검색 프리셋 (F-01-5)
    with st.expander("검색 프리셋"):
        mine = presets.list_presets(user.user_id)
        if mine:
            by_id = {p.id: p for p in mine}
            pid = st.selectbox(
                "저장된 프리셋", list(by_id), format_func=lambda i: by_id[i].name, key="preset_pick"
            )
            c1, c2 = st.columns(2)
            if c1.button("불러오기", width="stretch"):
                _apply_preset(by_id[pid])
                st.rerun()
            if c2.button("삭제", width="stretch"):
                presets.delete_preset(user.user_id, pid)
                st.rerun()
        else:
            st.caption("저장된 프리셋이 없습니다.")
        with st.form("preset_save", clear_on_submit=True):
            # 프리셋 '이름'만 입력받는다. 검색 조건으로 쓰이지 않는다 (불변규칙 3).
            name = st.text_input(
                "프리셋 이름",
                key="preset_name",
                max_chars=presets.MAX_NAME,
                placeholder="예: 감사위원 후보 – 여성 회계전문가",
            )
            if st.form_submit_button("현재 조건 저장"):
                try:
                    presets.save_preset(user.user_id, name, dict(f), state.get(state.K_RESULT_LIMIT))
                    st.success("저장했습니다.")
                except ValueError as exc:
                    st.warning(str(exc))

# ------------------------------------------------------------------ 결과 상단: 정렬·인원 수

top_left, top_right = st.columns(2)

with top_left:
    sort_items = CODES.load_codes(C.CODE_SORT)
    sort_options = [i.code for i in sort_items]
    sort_labels = {i.code: i.label for i in sort_items}
    sort_current = f.get("sort") or "FIT"
    sort_code = st.selectbox(
        "정렬 기준",
        sort_options,
        index=sort_options.index(sort_current) if sort_current in sort_options else 0,
        format_func=lambda c: sort_labels[c],
        key="w_sort",
    )
    state.set_filter("sort", sort_code)

with top_right:
    # 최대 조회 인원 수 (F-01-8, F-02-4). 사용자별 최근 선택값을 DB 에 기억한다.
    limit_items = CODES.load_codes(C.CODE_RESULT_LIMIT)
    limit_options = [i.code for i in limit_items]
    limit_labels = {i.code: i.label for i in limit_items}
    default_n = settings.get_int(C.SET_RESULT_LIMIT_DEFAULT)
    default_code = next(
        (i.code for i in limit_items if i.extra.get("value") == default_n), limit_options[0]
    )
    if state.get(state.K_RESULT_LIMIT) is None:
        state.put(
            state.K_RESULT_LIMIT,
            preferences.get_pref(user.user_id, preferences.KEY_RESULT_LIMIT) or default_code,
        )
    remembered = state.get(state.K_RESULT_LIMIT)
    limit_code = st.selectbox(
        "최대 조회 인원 수",
        limit_options,
        index=limit_options.index(remembered) if remembered in limit_options else 0,
        format_func=lambda c: limit_labels[c],
        help="정렬 기준을 적용한 뒤 상위 N명만 조회합니다. 화면 페이지 크기와는 별개입니다.",
        key="w_limit",
    )
    if limit_code != remembered:
        state.put(state.K_RESULT_LIMIT, limit_code)
        preferences.set_pref(user.user_id, preferences.KEY_RESULT_LIMIT, limit_code)

# ------------------------------------------------------------------ 조건 칩 (F-01-4)

chips: list[tuple[str, object, str]] = []
for key, label, category in SINGLE_FILTERS:
    if f.get(key):
        chips.append((key, f[key], f"{label}: {CODES.label_of(category, f[key])}"))
if f.get("job_scope") and f["job_scope"] != "BOTH":
    chips.append(("job_scope", f["job_scope"], f"직업 구분: {CODES.label_of(C.CODE_JOB_SCOPE, f['job_scope'])}"))
for key, label, category in MULTI_FILTERS:
    for value in f.get(key) or []:
        chips.append((key, value, f"{label}: {CODES.label_of(category, value)}"))

if chips:
    st.caption("적용 조건 (✕ 를 누르면 해당 조건만 해제)")
    cols = st.columns(4)
    for idx, (key, value, text) in enumerate(chips):
        cols[idx % 4].button(
            f"✕ {text}",
            key=f"chip_{key}_{value}",
            on_click=_remove_chip,
            args=(key, value),
            width="stretch",
        )
else:
    st.caption("적용 조건 — 전체")

# ------------------------------------------------------------------ 검색 실행

signature = json.dumps([f, limit_code], sort_keys=True, ensure_ascii=False, default=str)
if state.get(state.K_SIGNATURE) != signature:
    state.put(state.K_SIGNATURE, signature)
    state.put(state.K_PAGE, 1)
    st.session_state.pop("w_page", None)

requested_limit, _ = search.resolve_limit(limit_code, user.role)
if requested_limit >= 100:
    st.caption("조회 인원 수가 100명 이상이면 응답이 늦어질 수 있습니다. (PRD F-02-6)")

with st.spinner("검색 중…"):
    result = search.search(f, limit_code, user.role, page=state.get(state.K_PAGE, 1))

log_key = f"{signature}|{result.page}"
if state.get(state.K_LOGGED) != log_key:
    state.put(state.K_LOGGED, log_key)
    log_access(
        user.user_id,
        C.ACT_SEARCH,
        page="search",
        target_person_ids=[r.person_id for r in result.rows],
        detail=(
            f"matched={result.total_matched}, shown={result.shown}, limit={result.effective_limit}, "
            f"page={result.page}, filters={_filters_json()}"
        ),
    )

# ------------------------------------------------------------------ 결과 배너 (F-01-8, F-02-4)

if result.total_matched == 0:
    st.warning("조건에 해당하는 후보가 없습니다.")
    suggestions = search.relaxation_suggestions(f)
    if suggestions:
        st.markdown("**조건 완화 제안** (F-01-6)")
        for label, count in suggestions:
            st.markdown(f"- `{label}` 조건을 제외하면 **{count}명**")
elif result.truncated:
    if result.limit_capped_by == "system":
        st.warning(
            f"전체 매칭 **{result.total_matched:,}명** 중 상위 **{result.shown:,}명** 표시 — "
            f"조건에 해당하는 후보는 {result.total_matched:,}명이며 상한 {result.effective_limit:,}명까지만 "
            "표시합니다. 조건을 좁혀 주세요."
        )
    elif result.limit_capped_by == "viewer":
        st.warning(
            f"전체 매칭 **{result.total_matched:,}명** 중 상위 **{result.shown:,}명** 표시 — "
            f"외부뷰어 조회 상한 {result.effective_limit:,}명 적용"
        )
    else:
        st.warning(f"전체 매칭 **{result.total_matched:,}명** 중 상위 **{result.shown:,}명** 표시")
else:
    st.success(f"전체 매칭 **{result.total_matched:,}명** 전부 표시")

st.caption(scoring.DISCLAIMER)
if f.get("sort", "FIT") == "FIT" and not (f.get("expertise_l1") or f.get("expertise_l2")):
    st.caption("전문분야 조건을 선택하면 적합도에 전문분야 매칭도가 반영됩니다.")

# ------------------------------------------------------------------ 결과 목록 (F-02)

names = [r.name_ko for r in result.rows]


def _to_table(rows):
    out = []
    for r in rows:
        name = f"{r.name_ko} ({r.name_en})" if r.name_en else r.name_ko
        if names.count(r.name_ko) > 1:
            name += " ⚠동명이인"
        since = f" ({r.current_since.isoformat()}~)" if r.current_since else ""
        out.append(
            {
                "ID": r.person_id,
                "성명": name,
                "성별": {"M": "남", "F": "여"}.get(r.gender, "-"),
                "나이": (
                    f"만 {r.age}세{'(추정)' if r.age_estimated else ''} ({r.birth_year})" if r.age else "-"
                ),
                "현재 직업": f"{r.current_org or '-'} {r.current_title or ''}{since}".strip(),
                "전문분야": ", ".join(r.expertise_labels) or "-",
                "타사 등기임원": "없음" if r.concurrent_count == 0
                else f"{r.concurrent_count}개 ({r.directorship_summary})",
                "스크리닝": C.SCREEN_BADGE[r.screening],
                "적합도": scoring.display(r.fit_score),
                "적합도 근거": r.fit_basis or "-",
                "최종 갱신": r.updated_at.date().isoformat()
                + (" · 6개월 초과" if search.is_stale(r.updated_at) else ""),
            }
        )
    return out


normal = [r for r in result.rows if r.screening != C.SCREEN_FAIL]
failed = [r for r in result.rows if r.screening == C.SCREEN_FAIL]

if normal:
    st.dataframe(_to_table(normal), hide_index=True, width="stretch")

if failed:
    st.divider()
    st.subheader("결격 가능 후보 (별도 표시)")
    st.caption(
        "스크리닝에서 결격 가능으로 판정된 후보입니다. 적합도와 무관하게 목록 하단에 분리 표시하며, "
        "최종 판단은 법무 검토로 확정합니다. (PRD F-06)"
    )
    st.dataframe(_to_table(failed), hide_index=True, width="stretch")

# 페이지네이션: 조회 인원 수(N)와 페이지 크기는 별개 (F-02-5)
if result.page_count > 1:
    new_page = st.selectbox(
        "페이지",
        list(range(1, result.page_count + 1)),
        index=result.page - 1,
        format_func=lambda p: f"{p} / {result.page_count} 페이지",
        key="w_page",
        help=f"한 페이지 {result.page_size}건. 조회 인원 수와는 별개입니다.",
    )
    if new_page != result.page:
        state.put(state.K_PAGE, new_page)
        st.rerun()

# ------------------------------------------------------------------ 후보 이동

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    ids = [r.person_id for r in result.rows]
    if ids:
        picked = st.selectbox(
            "상세 볼 후보",
            ids,
            format_func=lambda pid: next(r.name_ko for r in result.rows if r.person_id == pid),
        )
        if st.button("후보 상세 열기", width="stretch"):
            state.put(state.K_SELECTED_PERSON, picked)
            st.switch_page("pages/2_후보_상세.py")
        if st.button("비교함에 담기 (최대 4명)", width="stretch"):
            basket = state.compare_basket()
            if picked in basket:
                st.info("이미 담겨 있습니다.")
            elif len(basket) >= 4:
                st.warning("비교는 최대 4명까지 가능합니다.")
            else:
                basket.append(picked)
                state.put(state.K_COMPARE_BASKET, basket)
                st.success("비교함에 담았습니다.")
with col_b:
    stage_notice("목록에서 여러 명 선택·POOL 저장·XLSX 내보내기는 다음 작업 단위(2-7)에서 구현합니다.")
