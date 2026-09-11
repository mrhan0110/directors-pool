"""S-04 후보 상세 프로파일 (PRD F-03, F-04-3·4, F-05-2·3·4, F-06).

- 모든 사실 항목 옆에 출처(발행처·문서명·발행일·URL·수집일)를 둔다 (F-05-1·2, F-09-6).
- 근거 스니펫이 없는 전문분야는 표시하지 않는다 (EXP.displayable, 불변규칙 2).
- 판정·집계 로직은 core/ 에 있고 이 파일은 표현만 담당한다.
"""

from __future__ import annotations

import streamlit as st

from core import access, career
from core import codes as CODES
from core import considerations as CS
from core import constants as C
from core import expertise as EXP
from core import reputation as REP
from core import scoring, screening, settings, state
from core import sources as SRC
from core.audit import log_access, log_denied
from core.auth import can_edit_pool, can_override_screening, can_review
from core.guard import confidential_notice, require
from core.ui import charts as UI_CHARTS
from core.ui.components import page_header, source_popover, term_gauge
from data import repository

user = require("detail")

page_header("후보 상세 프로파일")
confidential_notice()

# 후보 선택도 드롭다운으로 한다 (불변규칙 3). 외부뷰어는 공유받은 POOL 구성원만 (F-09-12)
options = access.filter_person_options(user, repository.list_person_options())
if not options:
    st.info(
        "열람 가능한 후보가 없습니다." if user.is_viewer
        else "후보 데이터가 없습니다. `python -m data.seed` 를 실행하세요."
    )
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
    key="detail_person",
)
if not access.can_view_person(user, picked):  # 이중 확인 (부록 C #3)
    log_denied(user.user_id, "detail", user.role)
    st.error("열람 권한이 없는 후보입니다.")
    st.stop()
state.put(state.K_SELECTED_PERSON, picked)

detail = repository.get_person_detail(picked)
if detail is None:
    st.warning("후보 정보를 찾을 수 없습니다.")
    st.stop()

log_access(user.user_id, C.ACT_VIEW, page="detail", target_person_ids=[picked])

p = detail.person
sources = detail.sources
policy = SRC.FreshnessPolicy.load()
conflicts = SRC.conflict_index(SRC.conflicts_of(picked))
score_row = scoring.get(picked)


def show_source(src, label: str = "출처") -> None:
    """출처 팝오버 (F-05-1·2, 3단계 §B) — 값 옆에서 바로 열어 확인한다."""
    source_popover(src, outdated=(src is not None and SRC.is_outdated(src, policy)), label=label)


def source_block(source_id: int) -> None:
    show_source(sources.get(source_id))


def conflict_note(entity: str, entity_id: int) -> None:
    """출처 간 상충 정보를 숨기지 않고 병기한다 (F-05-3)."""
    for c in conflicts.get((entity, entity_id), []):
        alt = c.alt_source
        st.caption(
            f"⚠ 대체 정보: {c.field} '{c.alt_value}' — {alt.publisher if alt else '출처 미상'}"
            f"({alt.source_tier if alt else '-'}등급). 상위 등급 출처의 '{c.adopted_value}'을(를) 채택했습니다."
        )
        show_source(alt, label="대체 정보 출처")


def source_cols(source_id: int) -> dict:
    src = sources.get(source_id)
    if src is None:
        return {"출처": None, "출처 정보": "출처 없음"}
    info = f"{src.publisher} · {src.published_date.isoformat() if src.published_date else '발행일 미상'} · {src.source_tier}등급"
    if SRC.is_outdated(src, policy):
        info += f" · {SRC.OUTDATED_LABEL}"
    return {"출처": src.url, "출처 정보": info}


LINK = {"출처": st.column_config.LinkColumn("출처", display_text="원문")}

# ------------------------------------------------------------------ 요약 헤더

status = screening.worst([screening.effective(s) for s in detail.screenings])
current = [pos for pos in detail.positions if pos.is_current]
h1, h2, h3, h4, h5 = st.columns(5)
h1.metric("성명", p.name_ko)
h2.metric("나이", f"만 {p.age()}세{'(추정)' if p.age_estimated_yn else ''}" if p.age() else "-")
h3.metric("스크리닝", C.SCREEN_BADGE[status])
h4.metric("적합도(기본)", scoring.display(score_row.base_score if score_row else None))
h5.metric("검수 상태", p.profile_status)
st.caption(
    (f"{p.name_en} · " if p.name_en else "")
    + "현직: " + (", ".join(f"{pos.org_name} {pos.title}" for pos in current) or "없음")
)
st.caption(scoring.DISCLAIMER)

if p.profile_status != C.PROFILE_REVIEWED:
    st.warning("검수 미완료 프로파일입니다. 외부 보고용 출력이 차단됩니다. (PRD F-08-1)", icon="⚠️")
if status == C.SCREEN_FAIL:
    st.warning("스크리닝에서 결격 가능 판정이 있습니다. 아래 ⑦의 룰별 판정과 법무 검토를 확인하세요.")

st.divider()

# ------------------------------------------------------------------ 경력 타임라인 (3단계 §E)

timeline_positions = sorted(
    (pos for pos in detail.positions if pos.start_date is not None),
    key=lambda pos: pos.start_date, reverse=True,
)[:15]
timeline = UI_CHARTS.career_timeline_chart(timeline_positions)
if timeline is not None:
    st.subheader("경력 타임라인")
    st.altair_chart(timeline, use_container_width=True)
    st.caption("최근 시작일 기준 최대 15건. 세부 근거는 각 섹션의 출처를 확인하세요.")
    st.divider()

# ------------------------------------------------------------------ 전문분야 (F-04-3·4)

st.subheader("전문분야 (자동 분류)")
shown_exp = sorted(EXP.displayable(detail.expertises, sources), key=lambda e: (not e.is_primary, -e.score))
if not shown_exp:
    st.caption("근거가 확인된 전문분야가 없습니다.")
for e in shown_exp:
    label = CODES.label_of(C.CODE_EXPERTISE_L2, e.taxonomy_code)
    st.markdown(
        f"**{label}** · {'대표' if e.is_primary else '보조'} · 신뢰도 {e.confidence} · 근거 {e.evidence_count}건"
        + (" · 담당자 확정" if e.confirmed_by_user_yn else "")
    )
    st.caption(f"근거: “{e.evidence_snippet}”")
    source_block(e.source_id)

if can_edit_pool(user.role) and shown_exp:
    with st.expander("전문분야 수정·확정 (PRD F-04-4)"):
        codes = [e.taxonomy_code for e in shown_exp]
        code = st.selectbox("대상 전문분야", codes, format_func=lambda c: CODES.label_of(C.CODE_EXPERTISE_L2, c))
        target = next(e for e in shown_exp if e.taxonomy_code == code)
        c1, c2 = st.columns(2)
        if c1.button("확정", disabled=target.confirmed_by_user_yn, width="stretch"):
            EXP.confirm(picked, code, user.user_id)
            st.rerun()
        if c2.button("보조로 지정" if target.is_primary else "대표로 지정", width="stretch"):
            try:
                EXP.set_primary(picked, code, not target.is_primary, user.user_id)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
        reason = st.text_input("삭제 사유 (필수)", key="exp_remove_reason")
        if st.button("이 전문분야 삭제"):
            try:
                EXP.remove(picked, code, user.user_id, reason)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
        hist = EXP.history_of(picked)[:10]
        if hist:
            st.dataframe(
                [{"일시": h.occurred_at.strftime("%Y-%m-%d %H:%M"), "전문분야": h.taxonomy_code,
                  "처리": h.action, "이전": h.before_value or "-", "이후": h.after_value or "-"} for h in hist],
                hide_index=True, width="stretch",
            )

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
    conflict_note("position", pos.position_id)
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
                f"{pos.end_date.isoformat() if pos.end_date else '미상'}",
                "기관": pos.org_name,
                "직위": pos.title,
                "등기/미등기": "등기" if pos.is_registered_officer else "미등기",
                "주요 역할": pos.duties or "-",
                **source_cols(pos.source_id),
            }
            for pos in view.recent
        ],
        hide_index=True,
        width="stretch",
        column_config=LINK,
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
        source_block(pos.source_id)

if view.excluded_count:
    st.caption(
        f"표출 기준(최근 {lookback}년 + 임원급 이상)에 해당하지 않아 제외된 이력 "
        f"{view.excluded_count}건이 있습니다."
    )

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
    imminent = []
    table = []
    for d in current_dirs:
        remaining = d.remaining_term_months()
        soon = remaining is not None and 0 <= remaining <= alert_months
        if soon:
            imminent.append(f"{d.company_name}({career.remaining_label(remaining)})")
        table.append(
            {
                "회사명": d.company_name,
                "상장": "상장" if d.listed_yn else "비상장",
                "직위": d.role_type,
                "선임일": d.appointed_date.isoformat() if d.appointed_date else "-",
                "임기 만료일": d.term_end_date.isoformat() if d.term_end_date else "미상",
                "잔여 임기": ("⚠ " if soon else "") + career.remaining_label(remaining),
                "위원회": ", ".join(d.committee_roles) or "-",
                "이사회 출석률": f"{d.board_attendance_rate:.0%}" if d.board_attendance_rate is not None else "-",
                **source_cols(d.source_id),
            }
        )
    if imminent:
        st.caption(f"잔여 임기 {alert_months}개월 이내 (PRD F-03-1)")
        for d in current_dirs:
            remaining = d.remaining_term_months()
            if remaining is not None and 0 <= remaining <= alert_months:
                term_gauge(remaining, alert_months, f"{d.company_name} · {d.role_type} — {career.remaining_label(remaining)}")
    st.dataframe(table, hide_index=True, width="stretch", column_config=LINK)
    st.caption("이사회 출석률은 직전 사업연도 사업보고서 공시 기준입니다. (PRD F-03-3)")

if past_dirs:
    with st.expander(f"종료된 등기임원 이력 {len(past_dirs)}건 (PRD F-03-4)"):
        st.dataframe(
            [
                {
                    "회사명": d.company_name,
                    "직위": d.role_type,
                    "선임일": d.appointed_date.isoformat() if d.appointed_date else "-",
                    "종료": d.term_end_date.isoformat() if d.term_end_date else "미상",
                    **source_cols(d.source_id),
                }
                for d in past_dirs
            ],
            hide_index=True,
            width="stretch",
            column_config=LINK,
        )

# ------------------------------------------------------------------ (5) 평판

st.subheader("⑤ 평판")
st.caption("확인된 사실만 판단에 사용합니다. 미확인 보도는 구분 표기하며 자동 점수에 반영하지 않습니다.")
if not detail.reputations:
    st.caption("수집된 평판 정보가 없습니다.")
else:
    sig = REP.signals(detail.reputations)
    s1, s2, s3 = st.columns(3)
    s1.metric("확인된 보도", f"{sig.verified}건")
    s2.metric("사실관계 미확인", f"{sig.unverified}건")
    s3.metric("확인된 부정 이슈", f"{sig.verified_negative}건")
    if sig.by_year:
        st.altair_chart(UI_CHARTS.reputation_trend_chart(sig.by_year), use_container_width=True)
        st.dataframe(
            [{"연도": y, **counts} for y, counts in sig.by_year.items()], hide_index=True, width="stretch"
        )
    if sig.topics:
        st.caption("주요 언급 주제: " + ", ".join(f"{t}({n})" for t, n in sig.topics))

    for r in detail.reputations:
        tag = {"긍정": "🟢", "중립": "⚪", "부정": "🔴"}.get(r.polarity, "⚪")
        verified = "확인됨" if r.verified_yn else "사실관계 미확인"
        st.markdown(f"{tag} **{r.category or r.polarity}** · {verified}")
        if r.polarity == "부정":
            parts = REP.status_parts(r)
            st.caption(" · ".join(f"{k}: {v}" for k, v in parts.items()))
        else:
            st.caption(f"{r.summary} · {r.event_date.isoformat() if r.event_date else '-'}")
        source_block(r.source_id)
st.caption("거버넌스 이력(과거 이사회 반대·기권 의결, 주총 부결·자문사 반대 권고): 수집된 이력 없음")

# ------------------------------------------------------------------ (6) 주요 업적

st.subheader("⑥ 주요 업적")
if not detail.achievements:
    st.caption("수집된 업적 정보가 없습니다.")
for a in detail.achievements:
    st.markdown(f"**{a.category or '-'}** · {a.description}")
    st.caption(f"{a.period or '-'} · 정량 지표: {a.quantitative_metric or '-'}")
    source_block(a.source_id)

# ------------------------------------------------------------------ (7) 선정 고려사항

st.subheader("⑦ 선정 고려사항")
st.caption("이사회 관리 담당자가 후보 선정 시 확인해야 할 18개 항목입니다. (PRD F-03 (7))")
items = CS.evaluate(detail, score_row.breakdown if score_row else None)
checks = CS.get_checks(picked)
st.dataframe(
    [
        {
            "#": it.no,
            "고려사항": it.title,
            "방식": it.mode,
            "자동 판정": C.SCREEN_BADGE.get(it.signal, "-") if it.signal else "수기 확인",
            "근거·참고": it.auto_text or "-",
            "수기 상태": checks[it.no].status if it.no in checks and checks[it.no].status else "-",
            "코멘트": checks[it.no].comment if it.no in checks and checks[it.no].comment else "-",
            "첨부": checks[it.no].attachment_name if it.no in checks and checks[it.no].attachment_name else "-",
        }
        for it in items
    ],
    hide_index=True,
    width="stretch",
)

if can_review(user.role):
    with st.form("consideration_form", clear_on_submit=True):
        st.markdown("**수기 확인·코멘트 등록** (PRD F-03-5)")
        titles = {it.no: it.title for it in items}
        no = st.selectbox("항목", list(titles), format_func=lambda n: f"{n}. {titles[n]}")
        chk_status = st.selectbox("확인 상태", CS.MANUAL_STATUSES)
        comment = st.text_area("코멘트")
        upload = st.file_uploader("첨부 (레퍼런스 체크 메모 등)")
        if st.form_submit_button("저장"):
            try:
                CS.save_check(
                    picked, no, user.user_id, status=chk_status, comment=comment,
                    attachment_name=upload.name if upload else None,
                    attachment=upload.getvalue() if upload else None,
                )
                st.success("저장했습니다.")
            except ValueError as exc:
                st.warning(str(exc))

with st.expander("스크리닝 룰별 판정 (PRD §5.1)"):
    if detail.screenings:
        st.dataframe(
            [
                {
                    "룰": s.rule_id,
                    "검증 항목": C.SCREENING_RULES.get(s.rule_id, "-"),
                    "자동 판정": C.SCREEN_BADGE.get(s.result, s.result),
                    "수기 판정": C.SCREEN_BADGE.get(s.reviewer_override, "-") if s.reviewer_override else "-",
                    "사유": s.reason or "-",
                    "수기 판정 사유": s.override_reason or "-",
                }
                for s in sorted(detail.screenings, key=lambda x: x.rule_id)
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("스크리닝 결과가 없습니다. 배치(`python -m batch.run analyze`)를 실행하세요.")
    st.caption("자동 판정은 1차 스크리닝이며 최종 적격성은 법무 검토로 확정합니다.")

    if can_override_screening(user.role) and detail.screenings:
        with st.form("override_form", clear_on_submit=True):
            st.markdown("**법무 수기 판정 입력**")
            rule_ids = [s.rule_id for s in sorted(detail.screenings, key=lambda x: x.rule_id)]
            rule_id = st.selectbox("룰", rule_ids, format_func=lambda r: f"{r} {C.SCREENING_RULES.get(r, '')}")
            choices = ["해제", C.SCREEN_PASS, C.SCREEN_WARN, C.SCREEN_FAIL]
            result = st.selectbox("판정", choices, format_func=lambda c: C.SCREEN_BADGE.get(c, "수기 판정 해제"))
            reason = st.text_area("판정 사유 (필수)")
            if st.form_submit_button("저장"):
                try:
                    screening.set_override(picked, rule_id, None if result == "해제" else result, reason)
                    scoring.store(picked)  # 리스크 감점 재산출
                    st.success("저장했습니다.")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
