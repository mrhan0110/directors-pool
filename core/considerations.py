"""선정 고려사항 체크리스트 18개 (PRD F-03 (7), F-03-5).

- 자동 판정 항목은 스크리닝·점수·수집 데이터에서 신호등과 근거 문구를 만든다.
  근거 데이터가 없으면 신호를 만들지 않고 '수기 확인'으로 둔다(추측 금지).
- 수기 항목은 ConsiderationCheck 에 상태·코멘트·첨부를 저장한다. 변경은 AuditLog 에 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select

from core import constants as C
from core import settings
from core.audit import log_change
from core.screening import effective, worst
from data.models import ConsiderationCheck
from data.session import session_scope

AUTO, MANUAL, BOTH = "자동", "수기", "자동+수기"

# (번호, 항목, 설명, 판정 방식) — PRD F-03 (7) 표 그대로
ITEMS: list[tuple[int, str, str, str]] = [
    (1, "독립성", "자사·계열사·최대주주와의 현재·과거 관계", AUTO),
    (2, "이해상충", "경쟁사 재직·자문, 주요 거래처 관계, 소송 상대방", BOTH),
    (3, "법적 결격사유", "§5.1 룰셋 전체 판정 결과", AUTO),
    (4, "오버보딩·가용시간", "총 겸직 수, 본업 상근 여부, 타사 이사회 개최 빈도", AUTO),
    (5, "성실성", "타사 이사회·위원회 출석률, 임기 중도 사임 이력", AUTO),
    (6, "재직 연수 상한", "자사 선임 시 잔여 가능 임기(연속·계열 합산 상한 대비)", AUTO),
    (7, "스킬 매트릭스 적합도", "현 이사회 역량 공백 대비 보완 정도", AUTO),
    (8, "다양성 기여", "성별·연령·경력 배경·국적 측면의 구성 개선 효과", AUTO),
    (9, "감사위원 적격", "회계·재무 전문가 요건, 분리선출 대상 여부", AUTO),
    (10, "규제기관 관계 리스크", "전관 논란 소지, 퇴직공직자 취업제한 심사 필요 여부", MANUAL),
    (11, "의결권 자문사 관점", "ISS·글래스루이스·국내 자문사 반대 권고 이력, 예상 쟁점", MANUAL),
    (12, "기관투자자 의결권 행사 기준", "국민연금 등 기관투자자 기준 저촉 가능성", MANUAL),
    (13, "물리적 가용성", "거주지·해외 체류, 이사회 참석 가능성, 사용 언어", BOTH),
    (14, "건강·연령 관련 정관 제한", "정관 제한 저촉 여부", MANUAL),
    (15, "보수 기대 수준", "현 겸직처 공시 보수 대비 자사 보수 정책 정합성", AUTO),
    (16, "평판 리스크의 잔존 여부", "언론 노출 가능성, 주총 반대표 유발 가능성", MANUAL),
    (17, "후보 수락 가능성", "접촉 이력, 추천 경로, 사전 의사 확인 결과", MANUAL),
    (18, "승계·연속성", "자사 이사회 임기 만료 일정과의 분산 정합성", AUTO),
]
ITEM_NOS = {no for no, *_ in ITEMS}

MANUAL_STATUSES = ("확인 전", "이상 없음", "확인 필요", "우려 있음")
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 레퍼런스 체크 메모 등 첨부 상한
PUBLIC_OFFICE_LOOKBACK_YEARS = 3        # 공직 경력 안내(수기 판단 보조) 기준 — 판정에 쓰지 않음


@dataclass(frozen=True)
class Consideration:
    no: int
    title: str
    description: str
    mode: str
    signal: str | None     # pass / warn / fail / info. None = 수기 확인 대상
    auto_text: str         # 자동 판정 근거 또는 수기 판단 보조 정보


def _rules(detail, *rule_ids: str) -> list[tuple[str, str, str | None]]:
    """(rule_id, 수기판정 반영 결과, 사유)."""
    return [
        (s.rule_id, effective(s), s.reason)
        for s in sorted(detail.screenings, key=lambda x: x.rule_id)
        if s.rule_id in rule_ids
    ]


def _from_rules(detail, *rule_ids: str) -> tuple[str | None, str]:
    rows = _rules(detail, *rule_ids)
    if not rows:
        return None, "스크리닝 미실행 — 배치 실행 후 확인"
    signal = worst([r for _, r, _ in rows])
    text = " / ".join(f"{rid}: {reason or '-'}" for rid, _, reason in rows)
    return signal, text


def evaluate(detail, score_breakdown: dict | None = None, today: date | None = None) -> list[Consideration]:
    today = today or date.today()
    current_dirs = [d for d in detail.directorships if d.is_current]
    out: dict[int, tuple[str | None, str]] = {}

    out[1] = _from_rules(detail, "R-01", "R-02")
    out[2] = _from_rules(detail, "R-03")

    legal = _rules(detail, "R-01", "R-02", "R-03", "R-04", "R-05", "R-06")
    if legal:
        fails = [rid for rid, r, _ in legal if r == C.SCREEN_FAIL]
        warns = [rid for rid, r, _ in legal if r == C.SCREEN_WARN]
        out[3] = (
            worst([r for _, r, _ in legal]),
            f"결격 가능 {len(fails)}건({', '.join(fails) or '-'}) · 확인 필요 {len(warns)}건({', '.join(warns) or '-'})",
        )
    else:
        out[3] = (None, "스크리닝 미실행 — 배치 실행 후 확인")

    signal4, text4 = _from_rules(detail, "R-04")
    full_time = [p for p in detail.positions if p.is_current and p.is_full_time]
    text4 += " · 본업 " + (", ".join(f"{p.org_name} {p.title}(상근)" for p in full_time) or "상근 직위 없음")
    out[4] = (signal4, text4 + " · 타사 이사회 개최 빈도는 수집 항목 없음")

    rates = [d.board_attendance_rate for d in current_dirs if d.board_attendance_rate is not None]
    threshold = settings.get_float(C.SET_ATTENDANCE_WARN_RATE)
    if rates:
        avg = sum(rates) / len(rates)
        out[5] = (
            C.SCREEN_WARN if avg < threshold else C.SCREEN_PASS,
            f"평균 출석률 {avg:.0%}(기준 {threshold:.0%}) · 중도 사임 이력은 수집 항목 없음 — 수기 확인",
        )
    else:
        out[5] = (None, "공시된 출석률 없음 — 수기 확인")

    out[6] = _from_rules(detail, "R-05")

    if score_breakdown and "skill_gap" in score_breakdown:
        sg = score_breakdown["skill_gap"]
        out[7] = (C.SCREEN_INFO, f"{sg['points']:.0f}/{sg['max']:.0f}점 — {sg['reason']}")
    else:
        out[7] = (None, "적합도 미산출 — 배치 실행 후 확인")

    signal8, text8 = _from_rules(detail, "R-08")
    p = detail.person
    extra8 = f" · 성별 {({'M': '남성', 'F': '여성'}).get(p.gender, '미상')}, 국적 {', '.join(p.nationality or []) or '-'}"
    out[8] = (C.SCREEN_INFO if signal8 else None, text8 + extra8)

    signal9, text9 = _from_rules(detail, "R-07")
    out[9] = (C.SCREEN_INFO if signal9 else None, text9 + " · 분리선출 대상 여부는 자사 기준으로 수기 확인")

    cutoff = date(today.year - PUBLIC_OFFICE_LOOKBACK_YEARS, today.month, min(today.day, 28))
    gov = [
        pos for pos in detail.positions
        if (pos.job_l1_code == "GOV") and (pos.is_current or (pos.end_date and pos.end_date >= cutoff))
    ]
    out[10] = (
        None,
        ("최근 공직 경력: " + ", ".join(f"{g.org_name} {g.title}" for g in gov) + " — 취업제한 심사 필요 여부 확인")
        if gov else "최근 공직 경력 없음(수집 기준)",
    )

    overseas = p.residence_region == "R_OVERSEAS" or (p.nationality_primary not in (None, "KR"))
    out[13] = (
        C.SCREEN_INFO if overseas else None,
        "해외 거주 또는 외국 국적 — 참석 가능성·사용 언어 확인" if overseas else "국내 거주·국적(수집 기준) — 참석 가능성 수기 확인",
    )

    comp = [d for d in current_dirs if d.compensation_disclosed]
    out[15] = (
        C.SCREEN_INFO if comp else None,
        ("공시 보수: " + ", ".join(f"{d.company_name} {d.compensation_disclosed / 10000:,.0f}만원" for d in comp))
        if comp else "공시 보수 없음",
    )

    soon = [d for d in current_dirs if d.term_end_date and today <= d.term_end_date <= today + timedelta(days=365)]
    out[18] = (
        C.SCREEN_INFO,
        ("1년 내 타사 임기 만료: " + ", ".join(f"{d.company_name}({d.term_end_date.isoformat()})" for d in soon))
        if soon else "1년 내 만료되는 타사 임기 없음 — 자사 임기 일정과 대조는 수기 확인",
    )

    result = []
    for no, title, desc, mode in ITEMS:
        signal, text = out.get(no, (None, ""))
        if mode == MANUAL:
            signal = None  # 수기 항목은 자동 신호를 만들지 않는다
        result.append(Consideration(no, title, desc, mode, signal, text))
    return result


# ------------------------------------------------------------------ 수기 확인 저장 (F-03-5)

def get_checks(person_id: int) -> dict[int, ConsiderationCheck]:
    with session_scope() as s:
        rows = s.execute(select(ConsiderationCheck).where(ConsiderationCheck.person_id == person_id)).scalars()
        return {r.item_no: r for r in rows}


def save_check(
    person_id: int,
    item_no: int,
    user_id: int | None,
    status: str | None = None,
    comment: str | None = None,
    attachment_name: str | None = None,
    attachment: bytes | None = None,
) -> None:
    if item_no not in ITEM_NOS:
        raise ValueError(f"고려사항 번호가 올바르지 않습니다: {item_no}")
    if status is not None and status not in MANUAL_STATUSES:
        raise ValueError(f"허용되지 않는 상태입니다: {status}")
    if attachment is not None and len(attachment) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"첨부파일은 {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB 이하만 등록할 수 있습니다.")
    with session_scope() as s:
        row = s.execute(
            select(ConsiderationCheck).where(
                ConsiderationCheck.person_id == person_id, ConsiderationCheck.item_no == item_no
            )
        ).scalar_one_or_none()
        if row is None:
            row = ConsiderationCheck(person_id=person_id, item_no=item_no)
            s.add(row)
        if status is not None:
            row.status = status
        if comment is not None:
            row.comment = comment.strip() or None
        if attachment is not None:
            row.attachment = attachment
            row.attachment_name = attachment_name or "첨부"
        row.updated_by = user_id
    log_change(user_id, "consideration", "update", f"{person_id}/{item_no}", status)
