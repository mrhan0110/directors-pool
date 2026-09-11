"""사추위 보고용 PDF (PRD 부록 A·B, F-03-6, F-09-17, 부록 C #9).

- 1인 2면 구성(내용이 많으면 3면): 1면 ①~④ / 2면 ⑤~⑧ / 각주 출처 목록
- 모든 사실 항목 끝에 [n] 각주 → 부록 B 형식 출처 목록
- 모든 면에 열람자·일시 워터마크와 '대외비 / 공개정보 기반 참고자료' 고지
- 근거 없는 전문분야와 미확인 평판은 수록하지 않는다
출력 가능 여부(검수·권한)는 reports.builder 가 판정한다. 이 모듈을 직접 부르지 말 것.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import career
from core import codes as CODES
from core import constants as C
from core import expertise as EXP
from core import reputation as REP
from core import scoring
from core.screening import effective, worst

NOTICE = "대외비 · 공개정보 기반 참고자료 · 최종 판단은 담당자·법무 검토로 확정"
SIGNAL_TEXT = {C.SCREEN_PASS: "이슈 없음", C.SCREEN_WARN: "확인 필요", C.SCREEN_FAIL: "결격 가능",
               C.SCREEN_INFO: "참고"}
CHECKLIST_ITEMS = (1, 2, 3, 4, 8, 7)  # 부록 A ⑦: 독립성·이해상충·결격·가용성·다양성·스킬갭

FONT_CANDIDATES = (
    os.getenv("PDF_FONT_PATH"),
    r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)
_font_name: str | None = None


def font_name() -> str:
    """한글 폰트. 환경변수 → 시스템 TTF → 내장 CID 폰트 순으로 폴백한다."""
    global _font_name
    if _font_name:
        return _font_name
    for path in FONT_CANDIDATES:
        if path and os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KR", path))
                _font_name = "KR"
                return _font_name
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    _font_name = "HYGothic-Medium"
    return _font_name


def _styles() -> dict[str, ParagraphStyle]:
    f = font_name()
    return {
        "title": ParagraphStyle("title", fontName=f, fontSize=14, leading=18, spaceAfter=4),
        "h": ParagraphStyle("h", fontName=f, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("body", fontName=f, fontSize=8.5, leading=11.5),
        "small": ParagraphStyle("small", fontName=f, fontSize=7, leading=9, textColor=colors.grey),
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "-")), style)


class Notes:
    """각주 번호 관리. 같은 출처는 같은 번호를 쓴다."""

    def __init__(self) -> None:
        self.sources: list = []

    def ref(self, src) -> str:
        if src is None:
            return ""
        for i, s in enumerate(self.sources, start=1):
            if s.source_id == src.source_id:
                return f"[{i}]"
        self.sources.append(src)
        return f"[{len(self.sources)}]"


def _table(rows: list[list], widths: list[float], st: dict) -> Table:
    data = [[_p(c, st["body"]) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


@dataclass
class CandidateDoc:
    detail: object
    score_row: object | None
    considerations: list
    opinion: str | None = None
    legal_review: str | None = None


def candidate_story(doc: CandidateDoc, st: dict, today: date | None = None) -> tuple[list, Notes]:
    today = today or date.today()
    d, p = doc.detail, doc.detail.person
    notes = Notes()
    src = d.sources.get
    story: list = [
        _p(f"사추위 보고용 후보 프로파일 — {p.name_ko}", st["title"]),
        _p(f"{p.name_en or ''} · 검수 상태 {p.profile_status} · 스크리닝 "
           f"{SIGNAL_TEXT[worst([effective(s) for s in d.screenings])]} · 적합도(보조 지표) "
           f"{scoring.display(doc.score_row.base_score if doc.score_row else None)}", st["small"]),
    ]

    # ① 기본정보
    story.append(_p("① 기본정보", st["h"]))
    edu = "; ".join(f"{e.get('school', '')} {e.get('major', '')} {e.get('degree', '')}".strip() for e in p.education or [])
    story.append(_table([
        ["성명", "성별", "만 나이", "국적", "학력", "자격"],
        [p.name_ko, {"M": "남", "F": "여"}.get(p.gender, "-"),
         f"{p.age()}세{'(추정)' if p.age_estimated_yn else ''}" if p.age() else "-",
         ", ".join(p.nationality or []) or "-", edu or "-", ", ".join(p.certifications or []) or "-"],
    ], [28, 12, 24, 16, 62, 38], st))

    # ② 현재 직업 및 주요 경력 (최근 10년, 임원급)
    story.append(_p("② 현재 직업 및 주요 경력 (최근 10년, 임원급)", st["h"]))
    current = [x for x in d.positions if x.is_current]
    view = career.build_view([x for x in d.positions if not x.is_current], today=today)
    rows = [["기간", "기관", "직위", "출처"]]
    for x in current:
        rows.append([f"{x.start_date or '-'} ~ 현재", x.org_name, x.title, notes.ref(src(x.source_id))])
    for x in view.recent:
        rows.append([f"{x.start_date or '-'} ~ {x.end_date or '미상'}", x.org_name, x.title, notes.ref(src(x.source_id))])
    story.append(_table(rows, [42, 62, 60, 16], st))
    for x in view.highlights:
        story.append(_p(f"주요 경력 하이라이트: {x.org_name} {x.title} ({x.start_date or '-'}~{x.end_date or '-'}) "
                        f"{notes.ref(src(x.source_id))}", st["small"]))

    # ③ 전문분야 3개 + 근거
    story.append(_p("③ 전문분야 (대표 3개) + 근거", st["h"]))
    exps = [e for e in EXP.displayable(d.expertises, d.sources) if e.is_primary][:3]
    if exps:
        story.append(_table(
            [["전문분야", "신뢰도·근거", "근거 요약", "출처"]]
            + [[CODES.label_of(C.CODE_EXPERTISE_L2, e.taxonomy_code), f"{e.confidence} · {e.evidence_count}건",
                e.evidence_snippet, notes.ref(src(e.source_id))] for e in exps],
            [38, 24, 102, 16], st))
    else:
        story.append(_p("근거가 확인된 전문분야 없음", st["body"]))

    # ④ 현 타사 등기임원 현황
    story.append(_p("④ 현 타사 등기임원 현황", st["h"]))
    dirs = [x for x in d.directorships if x.is_current]
    if dirs:
        story.append(_table(
            [["회사", "직위", "선임일", "임기만료", "잔여임기", "출석률", "출처"]]
            + [[x.company_name, x.role_type, x.appointed_date or "-", x.term_end_date or "미상",
                career.remaining_label(x.remaining_term_months(today)),
                f"{x.board_attendance_rate:.0%}" if x.board_attendance_rate is not None else "-",
                notes.ref(src(x.source_id))] for x in dirs],
            [38, 24, 22, 22, 26, 16, 16], st))
    else:
        story.append(_p("현재 수행 중인 타사 등기임원직 없음", st["body"]))

    story.append(PageBreak())

    # ⑤ 주요 업적
    story.append(_p("⑤ 주요 업적 (정량 지표 중심)", st["h"]))
    ach = sorted(d.achievements, key=lambda a: a.quantitative_metric is None)[:5]
    for a in ach:
        story.append(_p(f"· {a.description} — {a.quantitative_metric or '정량 지표 없음'} ({a.period or '-'}) "
                        f"{notes.ref(src(a.source_id))}", st["body"]))
    if not ach:
        story.append(_p("수집된 업적 없음", st["body"]))

    # ⑥ 평판 요약 — 확인된 사실만
    story.append(_p("⑥ 평판 요약 (확인된 사실만 수록)", st["h"]))
    positives = [r for r in d.reputations if r.verified_yn and r.polarity == "긍정"]
    negatives = [r for r in d.reputations if r.verified_yn and r.polarity == "부정"]
    unverified = sum(1 for r in d.reputations if not r.verified_yn)
    for r in positives:
        story.append(_p(f"긍정 근거: {r.category or '-'} · {r.summary} {notes.ref(src(r.source_id))}", st["body"]))
    for r in negatives:
        parts = REP.status_parts(r)
        story.append(_p(f"확인된 부정 이슈: {r.category or '-'} · " + " · ".join(f"{k} {v}" for k, v in parts.items())
                        + f" {notes.ref(src(r.source_id))}", st["body"]))
    if not positives and not negatives:
        story.append(_p("확인된 평판 사항 없음", st["body"]))
    if unverified:
        story.append(_p(f"사실관계 미확인 보도 {unverified}건은 수록하지 않았습니다.", st["small"]))

    # ⑦ 선정 고려사항 체크리스트
    story.append(_p("⑦ 선정 고려사항 체크리스트", st["h"]))
    by_no = {c.no: c for c in doc.considerations}
    rows = [["항목", "판정", "근거"]]
    for no in CHECKLIST_ITEMS:
        c = by_no.get(no)
        if c:
            rows.append([c.title, SIGNAL_TEXT.get(c.signal, "수기 확인"), (c.auto_text or "-")[:180]])
    story.append(_table(rows, [34, 20, 126], st))

    # ⑧ 종합 의견 / 법무 검토 결과
    story.append(_p("⑧ 종합 의견 / 법무 검토 결과", st["h"]))
    story.append(_table([["종합 의견(담당자)", "법무 검토 결과"],
                         [doc.opinion or "(작성란)", doc.legal_review or "(작성란)"]], [90, 90], st))

    # 각주
    story.append(_p("출처", st["h"]))
    for i, s in enumerate(notes.sources, start=1):
        story.append(_p(f"[{i}] {s.citation()}", st["small"]))
    return story, notes


def stamp(viewer_label: str, generated_at: datetime) -> str:
    return f"대외비 · 열람자 {viewer_label} · {generated_at:%Y-%m-%d %H:%M}"


def _decorate(text: str):
    def on_page(canvas, doc):
        f = font_name()
        w, h = A4
        canvas.saveState()
        canvas.setFont(f, 22)
        canvas.setFillColor(colors.Color(0.55, 0.55, 0.55, alpha=0.16))
        canvas.translate(w / 2, h / 2)
        canvas.rotate(35)
        canvas.drawCentredString(0, 0, text)
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont(f, 7)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(w - 15 * mm, h - 10 * mm, "대외비")
        canvas.drawString(15 * mm, 9 * mm, f"{NOTICE} · {text.removeprefix('대외비 · ')}")
        canvas.drawRightString(w - 15 * mm, 9 * mm, str(doc.page))
        canvas.restoreState()
    return on_page


def render(story: list, viewer_label: str, generated_at: datetime, title: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=16 * mm, title=title, author="독립이사 후보자 POOL")
    deco = _decorate(stamp(viewer_label, generated_at))
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


def render_candidates(docs: list[CandidateDoc], viewer_label: str, generated_at: datetime, title: str,
                      summary_rows: list[list] | None = None) -> bytes:
    st = _styles()
    story: list = []
    if summary_rows:
        story += [_p(title, st["title"]), _p("POOL 요약표", st["h"]),
                  _table(summary_rows, [50, 30, 30, 30, 40], st), PageBreak()]
    for i, doc in enumerate(docs):
        part, _ = candidate_story(doc, st)
        story += part
        if i < len(docs) - 1:
            story.append(PageBreak())
    return render(story, viewer_label, generated_at, title)
