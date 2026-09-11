"""리포트 생성 인터페이스 (PRD 부록 A·B). 구현은 2단계 I 항목.

1단계에서 고정해 두는 것: 출력 게이트.
검수 미완료 프로파일과 다운로드 권한 없는 역할은 출력 자체가 불가하다.
(PRD F-08-1, F-09-9, F-09-12)
"""

from __future__ import annotations

from dataclasses import dataclass

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


def build_candidate_pdf(person_id: int, viewer_label: str) -> bytes:  # pragma: no cover
    raise NotImplementedError(
        "사추위 보고용 PDF 는 2단계(I)에서 구현합니다. "
        "부록 A 2페이지 템플릿 + 부록 B 출처 각주 + 열람자 워터마크가 필수입니다."
    )


def build_pool_xlsx(pool_id: int, viewer_label: str) -> bytes:  # pragma: no cover
    raise NotImplementedError(
        "POOL XLSX 는 2단계(B/I)에서 구현합니다. "
        "출처 URL 컬럼과 조회 조건·인원수·일시 기록이 필수입니다. (PRD F-02-3)"
    )
