"""S-04 후보 상세 프로파일 (PRD F-03).

모든 사실 항목에는 출처 접근 경로가 함께 있어야 한다 (F-05-2).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import career, codes as CODES, constants as C, settings, state
from core.audit import log_access
from core.guard import confidential_notice, require, stage_notice
from data import repository

user = require("detail")

st.title("후보 상세 프로파일")
confidential_notice()

# 후보 선택도 드롭다운으로 한다 (불변규칙 3)
options = repository.list_person_options()
if not options:
    st.info("후보 데이터가 없습니다. `python -m data.seed` 를 실행하세요.")
    st.stop()

name_by_id = dict(options)
selected = state.get(state.K_SELECTED_PERSON) or options[0][0]
if selected not in name_by_id:
    selected = options[0][0]

picked = st.selectbox(
    "후보 선택",
    list(name_by_id.keys()),
    index=list(name_by_id.keys()).index(selected),
    format_func=lambda pid: name_by_id[pid],
)
state.put(state.K_SELECTED_PERSON, picked)

detail = repository.get_person_detail(picked)
if detail is None:
    st.error("후보 정보를 찾을 수 없습니다.")
    st.stop()

log_access(user.user_id, C.ACT_VIEW, page="detail", target_person_ids=[picked])

p = detail.person
sources = detail.sources


def source_block(source_id: int) -> None:
    src = sources.get(source_id)
    if src is None:
        st.error("출처 정보가 없습니다. 표시되어서는 안 되는 데이터입니다. (PRD F-05-1)")
        return
    with st.expander("출처 보기"):
        st.markdown(f"**{src.publisher}** · 「{src.doc_title}」")
        st.caption(
            f"발행일 {src.published_date.isoformat() if src.published_date else '미상'}"
            f" · 신뢰등급 {src.source_tier}"
            f" · 수집일 {src.collected_at.date().isoformat()}"
        )
        st.markdown(f"[{src.url}]({src.url})")
        if src.quote_snippet:
            st.caption(f"인용: {src.quote_snippet}")


# ------------------------------------------------------------------ 요약 헤더
badge = C.SCREEN_BADGE[
    max(
        (s.result for s in detail.screenings),
        key=lambda r: C.SCREEN_ORDER.get(r, 0),
        default=C.SCREEN_PASS,
    )
]
h1, h2, h3, h4 = st.columns(4)
h1.metric("성명", p.name_ko)
h2.metric("나이", f"만 {p.age()}세{'(추정)' if p.age_estimated_yn else ''}" if p.age() else "-")
h3.metric("스크리닝", badge)
h4.metric("검수 상태", p.profile_status)

if p.profile_status != C.PROFILE_REVIEWED:
    st.warning("검수 미완료 프로파일입니다. 외부 보고용 출력이 차단됩니다. (PRD F-08-1)", icon="⚠️")

st.divider()

# ------------------------------------------------------------------ (1) 기본 정보
st.subheader("① 기본 정보")
b1, b2 = st.columns(2)
with b1:
    st.write(f"**성별** {'남성' if p.gender == 'M' else '여성' if p.gender == 'F' else '-'}")
    st.write(f"**출생연도** {p.birth_year or '-'}")
    st.write(
        "**국적** "
        + ", ".join(CODES.label_of(C.CODE_NATIONALITY, n) for n in (p.nationality or []))
        + (" (복수국적)" if p.multi_nationality_yn else "")
    )
    st.write(f"**활동 지역** {CODES.label_of(C.CODE_REGION, p.residence_region)}")
with b2:
    for edu in p.education or []:
        st.write(f"**학력** {edu.get('school', '-')} {edu.get('major', '')} {edu.get('degree', '')}")
    st.write("**보유 자격** " + (", ".join(p.certifications or []) or "-"))
    st.write(
        "**산업 도메인 경험** "
        + (", ".join(CODES.label_of(C.CODE_INDUSTRY, c) for c in detail.industries) or "-")
    )

# ------------------------------------------------------------------ (2) 현재 직업
st.subheader("② 현재 직업")
current = [pos for pos in detail.positions if pos.is_current]
if not current:
    st.caption("현직 정보가 없습니다.")
for pos in current:
    st.markdown(f"**{pos.org_name}** · {pos.title}")
    st.caption(
        f"{'상근' if pos.is_full_time else '비상근'}"
        f" · 재직 시작 {pos.start_date.isoformat() if pos.start_date else '-'}"
        f" · {'등기임원' if pos.is_registered_officer else '미등기'}"
        + (f" · 임기 만료 예정 {pos.term_end_date.isoformat()}" if pos.term_end_date else "")
    )
    if pos.duties:
        st.caption(f"담당 업무: {pos.duties}")
    source_block(pos.source_id)

# ------------------------------------------------------------------ (3) 과거 직업
lookback = settings.get_int(C.SET_CAREER_LOOKBACK_YEARS)
st.subheader(f"③ 과거 직업 — 최근 {lookback}개년, 임원급 이상 주요 보직")
view = career.build_view([pos for pos in detail.positions if not pos.is_current])
if view.recent:
    st.dataframe(
        [
            {
                "기간": f"{pos.start_date.isoformat() if pos.start_date else '-'} ~ "
                f"{pos.end_date.isoformat() if pos.end_date else '현재'}",
                "기관": pos.org_name,
                "직위": pos.title,
                "등기/미등기": "등기" if pos.is_registered_officer else "미등기",
                "주요 역할": pos.duties or "-",
            }
            for pos in view.recent
        ],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.caption("표출 기준에 해당하는 과거 경력이 없습니다.")

if view.highlights:
    st.markdown("**주요 경력 하이라이트** (표출 기간 초과이나 판단에 결정적인 이력)")
    for pos in view.highlights:
        st.write(
            f"- {pos.start_date.year if pos.start_date else '-'}"
            f"~{pos.end_date.year if pos.end_date else '-'} · {pos.org_name} {pos.title}"
        )

if view.excluded_count:
    st.caption(
        f"표출 기준(최근 {lookback}년 + 임원급 이상)에 해당하지 않아 제외된 이력 "
        f"{view.excluded_count}건이 있습니다."
    )
stage_notice("경력 타임라인 시각화는 3단계(C)에서 추가합니다.")

# ------------------------------------------------------------------ (4) 타사 등기임원
st.subheader("④ 현재 타사 등기임원 수행 현황")
limit = settings.get_int(C.SET_CONCURRENT_LIMIT)
alert_months = settings.get_int(C.SET_TERM_ALERT_MONTHS)
current_dirs = [d for d in detail.directorships if d.is_current]
past_dirs = [d for d in detail.directorships if not d.is_current]

listed_count = sum(1 for d in current_dirs if d.listed_yn)
if listed_count > limit:
    st.error(
        f"⚠️ 오버보딩 경고 — 타사 상장사 등기임원 {listed_count}건으로 사내 설정 한도"
        f"({limit}건)를 초과합니다. (PRD F-03-2)"
    )

if not current_dirs:
    st.caption("현재 수행 중인 타사 등기임원직이 없습니다.")
else:
    for d in current_dirs:
        remaining = d.remaining_term_months()
        if remaining is None:
            remain_label = "임기 만료일 미상"
        elif remaining < 0:
            remain_label = f"이미 만료 ({abs(remaining)}개월 경과)"
        else:
            remain_label = f"{remaining // 12}년 {remaining % 12}개월"

        header = f"**{d.company_name}** ({'상장' if d.listed_yn else '비상장'}) · {d.role_type}"
        if remaining is not None and 0 <= remaining <= alert_months:
            st.markdown(f"{header} — :red[잔여 {remain_label}]")
        else:
            st.markdown(f"{header} — 잔여 {remain_label}")
        st.caption(
            f"선임일 {d.appointed_date.isoformat() if d.appointed_date else '-'}"
            f" · 임기 만료 {d.term_end_date.isoformat() if d.term_end_date else '미상'}"
            f" · 위원회 {', '.join(d.committee_roles) or '-'}"
            f" · 직전 사업연도 이사회 출석률 "
            f"{f'{d.board_attendance_rate:.0%}' if d.board_attendance_rate is not None else '-'}"
        )
        source_block(d.source_id)

if past_dirs:
    with st.expander(f"종료된 등기임원 이력 {len(past_dirs)}건"):
        for d in past_dirs:
            st.write(f"- {d.company_name} · {d.role_type}")

# ------------------------------------------------------------------ (5) 평판
st.subheader("⑤ 평판")
if not detail.reputations:
    st.caption("수집된 평판 정보가 없습니다.")
for r in detail.reputations:
    tag = {"긍정": "🟢", "중립": "⚪", "부정": "🔴"}.get(r.polarity, "⚪")
    verified = "확인됨" if r.verified_yn else "사실관계 미확인"
    st.markdown(f"{tag} **{r.category or r.polarity}** · {r.summary}")
    st.caption(
        f"{r.event_date.isoformat() if r.event_date else '-'}"
        f" · 진행경과 {r.status or '-'} · {verified}"
    )
    if not r.verified_yn:
        st.caption("※ 미확인 건은 평판 점수에 반영하지 않습니다. (PRD F-03 (5))")
    source_block(r.source_id)

# ------------------------------------------------------------------ (6) 주요 업적
st.subheader("⑥ 주요 업적")
if not detail.achievements:
    st.caption("수집된 업적 정보가 없습니다.")
for a in detail.achievements:
    st.markdown(f"**{a.category or '-'}** · {a.description}")
    st.caption(f"{a.period or '-'} · 지표: {a.quantitative_metric or '-'}")
    source_block(a.source_id)

# ------------------------------------------------------------------ (7) 선정 고려사항
st.subheader("⑦ 선정 고려사항")
st.caption("이사회 관리 담당자가 후보 선정 시 확인해야 할 항목입니다. (PRD F-03 (7), 18개 항목)")
if detail.screenings:
    st.dataframe(
        [
            {
                "룰": s.rule_id,
                "검증 항목": C.SCREENING_RULES.get(s.rule_id, "-"),
                "판정": C.SCREEN_BADGE.get(s.result, s.result),
                "사유": s.reason or "-",
            }
            for s in sorted(detail.screenings, key=lambda x: x.rule_id)
        ],
        hide_index=True,
        use_container_width=True,
    )
stage_notice(
    "고려사항 18개 체크리스트(자동 판정 신호등 + 수기 확인란 + 코멘트/첨부)는 "
    "2단계(C·E)에서 구현합니다. 현재는 더미 스크리닝 판정만 표시합니다."
)
