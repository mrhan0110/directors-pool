"""S-02 후보 검색 (PRD F-01, F-02).

모든 조건은 드롭다운이다. 키워드 입력창을 만들지 않는다. (불변규칙 3)
"""

from __future__ import annotations

import streamlit as st

from core import codes as CODES
from core import constants as C
from core import scoring, search, settings, state
from core.audit import log_access
from core.guard import confidential_notice, require, stage_notice

user = require("search")

st.title("후보 검색")
confidential_notice()

f = state.filters()


def _select(label: str, category: str, filter_key: str, help_text: str | None = None) -> None:
    """단일 선택 드롭다운. '전체'가 기본값이며 미선택 시 조건에서 제외한다 (F-01-1)."""
    items = CODES.load_codes(category)
    options = [CODES.ALL] + [i.code for i in items]
    labels = {CODES.ALL: CODES.ALL_LABEL, **{i.code: i.label for i in items}}
    current = f.get(filter_key) or CODES.ALL
    picked = st.selectbox(
        label,
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda c: labels[c],
        key=f"sel_{filter_key}",
        help=help_text,
    )
    state.set_filter(filter_key, None if picked == CODES.ALL else picked)


def _multi(
    label: str,
    category: str,
    filter_key: str,
    parent_code: str | None = None,
    parent_codes: list[str] | None = None,
    max_selections: int | None = None,
    help_text: str | None = None,
) -> None:
    if parent_codes:
        items = [i for code in parent_codes for i in CODES.load_codes(category, parent_code=code)]
    else:
        items = CODES.load_codes(category, parent_code=parent_code)
    options = [i.code for i in items]
    labels = {i.code: i.label for i in items}
    current = [c for c in (f.get(filter_key) or []) if c in options]
    picked = st.multiselect(
        label,
        options,
        default=current,
        format_func=lambda c: labels.get(c, c),
        key=f"multi_{filter_key}",
        max_selections=max_selections,
        placeholder="전체",
        help=help_text,
    )
    state.set_filter(filter_key, picked)


with st.sidebar:
    st.subheader("검색 조건")
    st.caption("모든 조건은 선택식입니다.")

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
        horizontal=False,
        key="radio_job_scope",
    )
    state.set_filter("job_scope", scope)

    prev_l1 = list(f.get("job_l1") or [])
    _multi("직업 — 대분류", C.CODE_JOB_L1, "job_l1")
    if list(f.get("job_l1") or []) != prev_l1:
        # 상위가 바뀌면 하위 선택을 초기화한다 (F-01-2)
        state.clear_dependent("job_l1")
        st.session_state.pop("multi_job_l2", None)
    if f.get("job_l1"):
        _multi("직업 — 중분류", C.CODE_JOB_L2, "job_l2", parent_codes=list(f["job_l1"]))
    _multi("직급 수준", C.CODE_ROLE_LEVEL, "role_levels")

    st.markdown("**전문분야**")
    prev_exp1 = list(f.get("expertise_l1") or [])
    _multi("전문분야 — 대분류", C.CODE_EXPERTISE_L1, "expertise_l1")
    if list(f.get("expertise_l1") or []) != prev_exp1:
        state.clear_dependent("expertise_l1")
        st.session_state.pop("multi_expertise_l2", None)
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
    if st.button("조건 초기화", use_container_width=True):
        state.reset_filters()
        for key in list(st.session_state.keys()):
            if key.startswith(("sel_", "multi_", "radio_")):
                st.session_state.pop(key, None)
        st.rerun()

# ------------------------------------------------------------------ 결과 영역

top_left, top_mid, top_right = st.columns([2, 2, 2])

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
    )
    state.set_filter("sort", sort_code)

with top_mid:
    # 최대 조회 인원 수 (PRD F-01-8). 최근 선택값을 사용자별로 기억한다.
    limit_items = CODES.load_codes(C.CODE_RESULT_LIMIT)
    limit_options = [i.code for i in limit_items]
    limit_labels = {i.code: i.label for i in limit_items}
    default_n = settings.get_int(C.SET_RESULT_LIMIT_DEFAULT)
    default_code = next(
        (i.code for i in limit_items if i.extra.get("value") == default_n), limit_options[0]
    )
    remembered = state.get(state.K_RESULT_LIMIT) or default_code
    limit_code = st.selectbox(
        "최대 조회 인원 수",
        limit_options,
        index=limit_options.index(remembered) if remembered in limit_options else 0,
        format_func=lambda c: limit_labels[c],
        help="정렬 기준을 적용한 뒤 상위 N명만 조회합니다.",
    )
    state.put(state.K_RESULT_LIMIT, limit_code)

with top_right:
    st.write("")
    run_search = st.button("검색", type="primary", use_container_width=True)

applied = []
for key, label, category in [
    ("gender", "성별", C.CODE_GENDER),
    ("concurrent", "겸직 수", C.CODE_CONCURRENT),
    ("term_remain", "잔여임기", C.CODE_TERM_REMAIN),
    ("screening", "스크리닝", C.CODE_SCREENING),
    ("reputation", "평판", C.CODE_REPUTATION),
    ("freshness", "최신성", C.CODE_FRESHNESS),
]:
    if f.get(key):
        applied.append(f"{label}: {CODES.label_of(category, f[key])}")
for key, label, category in [
    ("age_bands", "연령", C.CODE_AGE_BAND),
    ("job_l1", "직업", C.CODE_JOB_L1),
    ("job_l2", "직업(중)", C.CODE_JOB_L2),
    ("role_levels", "직급", C.CODE_ROLE_LEVEL),
    ("expertise_l1", "전문분야", C.CODE_EXPERTISE_L1),
    ("expertise_l2", "전문분야(중)", C.CODE_EXPERTISE_L2),
    ("industries", "산업", C.CODE_INDUSTRY),
    ("nationalities", "국적", C.CODE_NATIONALITY),
    ("regions", "지역", C.CODE_REGION),
]:
    values = f.get(key) or []
    if values:
        applied.append(f"{label}: " + ", ".join(CODES.label_of(category, v) for v in values))

st.caption("적용 조건 — " + (" | ".join(applied) if applied else "전체"))

result = search.search(f, limit_code, user.role)
log_access(
    user.user_id,
    C.ACT_SEARCH,
    page="search",
    detail=f"matched={result.total_matched}, shown={result.shown}, limit={result.effective_limit}",
)

# 결과가 잘렸음을 항상 명시한다 (PRD F-01-8)
if result.total_matched == 0:
    st.warning("조건에 해당하는 후보가 없습니다.")
    suggestions = search.relaxation_suggestions(f)
    if suggestions:
        st.markdown("**조건 완화 제안**")
        for label, count in suggestions:
            st.markdown(f"- `{label}` 조건을 제외하면 **{count}명**")
else:
    if result.shown < result.total_matched:
        msg = f"전체 매칭 **{result.total_matched:,}명** 중 상위 **{result.shown:,}명** 표시"
        if result.limit_capped_by == "system":
            msg += f" · 시스템 상한 {result.effective_limit}명 적용 — 조건을 좁혀 주세요"
        elif result.limit_capped_by == "viewer":
            msg += f" · 외부뷰어 조회 상한 {result.effective_limit}명 적용"
        st.warning(msg)
    else:
        st.success(f"전체 매칭 **{result.total_matched:,}명** 전부 표시")

if result.sort_code == "FIT":
    st.caption(
        f"적합도 점수는 2단계에서 산출됩니다({scoring.NOT_IMPLEMENTED_LABEL}). "
        "현재 정렬은 데이터 최신순으로 동작합니다."
    )

normal = [r for r in result.rows if r.screening != C.SCREEN_FAIL]
failed = [r for r in result.rows if r.screening == C.SCREEN_FAIL]


def _to_table(rows):
    return [
        {
            "ID": r.person_id,
            "성명": r.name_ko,
            "성별": {"M": "남", "F": "여"}.get(r.gender, "-"),
            "나이": f"만 {r.age}세{'(추정)' if r.age_estimated else ''}" if r.age else "-",
            "현재 직업": f"{r.current_org or '-'} {r.current_title or ''}".strip(),
            "전문분야": ", ".join(r.expertise_labels) or "-",
            "타사 등기임원": f"{r.concurrent_count}개 ({r.directorship_summary})",
            "스크리닝": C.SCREEN_BADGE[r.screening],
            "적합도": scoring.NOT_IMPLEMENTED_LABEL,
            "최종 갱신": r.updated_at.date().isoformat(),
        }
        for r in rows
    ]


if normal:
    st.dataframe(_to_table(normal), hide_index=True, use_container_width=True)

if failed:
    st.divider()
    st.subheader("결격 가능 후보 (별도 표시)")
    st.caption(
        "스크리닝에서 결격 가능으로 판정된 후보입니다. 적합도와 무관하게 분리 표시하며, "
        "최종 판단은 법무 검토로 확정합니다. (PRD F-06)"
    )
    st.dataframe(_to_table(failed), hide_index=True, use_container_width=True)

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
        if st.button("후보 상세 열기", use_container_width=True):
            state.put(state.K_SELECTED_PERSON, picked)
            st.switch_page("pages/2_후보_상세.py")
        if st.button("비교함에 담기 (최대 4명)", use_container_width=True):
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
    stage_notice("POOL 저장·XLSX 내보내기·항목별 건수 배지는 2단계(B)에서 구현합니다.")
