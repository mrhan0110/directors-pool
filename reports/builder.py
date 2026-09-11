"""리포트 생성 진입점 (PRD 부록 A·B, F-03-6, F-07, F-08-1, F-09-9·12).

화면은 반드시 이 모듈을 거쳐 출력한다. 게이트(검수 완료 + 다운로드 권한)를 여기서 다시 검사하므로
화면의 버튼 비활성화가 우회되더라도 파일이 만들어지지 않는다(이중 방어).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core import constants as C
from core.auth import can_download


class ExportBlockedError(PermissionError):
    pass


@dataclass(frozen=True)
class ExportGate:
    allowed: bool
    reason: str | None = None


def check_export(role: str | None, profile_statuses: list[str]) -> ExportGate:
    """출력 가능 여부를 판정한다. 화면은 이 결과로 버튼 활성/비활성과 사유를 표시한다."""
    if not can_download(role):
        return ExportGate(False, "외부뷰어 역할은 자료를 다운로드할 수 없습니다. (PRD F-09-12)")
    unreviewed = [s for s in profile_statuses if s != C.PROFILE_REVIEWED]
    if unreviewed:
        return ExportGate(
            False,
            f"검수 미완료 프로파일 {len(unreviewed)}건이 포함되어 있어 출력할 수 없습니다. "
            f"검수 화면에서 승인 후 다시 시도하세요. (PRD F-08-1)",
        )
    return ExportGate(True)


def _candidate_doc(person_id: int, opinion: str | None = None, legal_review: str | None = None):
    from core import considerations as CS
    from core import scoring
    from data.repository import get_person_detail
    from reports.pdf import CandidateDoc

    detail = get_person_detail(person_id)
    if detail is None:
        raise LookupError(f"후보를 찾을 수 없습니다: {person_id}")
    score_row = scoring.get(person_id)
    items = CS.evaluate(detail, score_row.breakdown if score_row else None)
    return CandidateDoc(detail, score_row, items, opinion, legal_review)


def build_candidate_pdf(
    person_id: int,
    role: str | None,
    viewer_label: str,
    opinion: str | None = None,
    legal_review: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """사추위 보고용 1인 프로파일 PDF."""
    from reports.pdf import render_candidates

    doc = _candidate_doc(person_id, opinion, legal_review)
    gate = check_export(role, [doc.detail.person.profile_status])
    if not gate.allowed:
        raise ExportBlockedError(gate.reason)
    return render_candidates([doc], viewer_label, generated_at or datetime.now(),
                             title=f"사추위 보고용 프로파일 — {doc.detail.person.name_ko}")


def build_pool_pdf(
    pool_id: int,
    role: str | None,
    viewer_label: str,
    generated_at: datetime | None = None,
) -> bytes:
    """POOL 단위 리포트: 요약표 + 개인별 프로파일 (PRD F-07). 전원 검수완료여야 한다."""
    from core import pools, scoring
    from core.screening import effective, worst
    from reports.pdf import SIGNAL_TEXT, render_candidates

    pool = pools.get_pool(pool_id)
    if pool is None:
        raise LookupError(f"POOL 이 없습니다: {pool_id}")
    members = pools.members(pool_id)
    if not members:
        raise ValueError("POOL 에 후보가 없습니다.")
    gate = check_export(role, [m.profile_status for m in members])
    if not gate.allowed:
        raise ExportBlockedError(gate.reason)
    docs = [_candidate_doc(m.person_id) for m in members]
    summary = [["후보", "POOL 상태", "스크리닝", "적합도", "검수"]]
    for m, d in zip(members, docs):
        summary.append([
            m.name_ko, m.state, SIGNAL_TEXT[worst([effective(s) for s in d.detail.screenings])],
            scoring.display(d.score_row.base_score if d.score_row else None), m.profile_status,
        ])
    return render_candidates(docs, viewer_label, generated_at or datetime.now(),
                             title=f"POOL 리포트 — {pool.name}", summary_rows=summary)
