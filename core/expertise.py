"""전문분야 분류 (PRD F-04). 자동 분류 로직은 2단계 D 항목이다.

1단계에서 미리 박아 두는 것: 근거 없는 분류를 막는 가드.
Expertise.evidence_snippet 이 NOT NULL 이지만, 공백 문자열까지는 DB 가 막지 못하므로
쓰기 경로에서 한 번 더 검증한다. (불변규칙 2, PRD F-04-2)
"""

from __future__ import annotations

from core import codes as CODES
from core import constants as C
from data.models import Expertise

MAX_PRIMARY = 3  # 대표 전문분야 최대 개수 (PRD F-04)

# 근거 최신성 가중 (PRD §6.4 분류 로직 3)
RECENCY_WEIGHTS = ((5, 1.0), (10, 0.6), (None, 0.3))
# 출처 신뢰도 가중
TIER_WEIGHTS = {C.SOURCE_TIER_A: 1.0, C.SOURCE_TIER_B: 0.8, C.SOURCE_TIER_C: 0.5}


class MissingEvidenceError(ValueError):
    """근거 스니펫 없이 전문분야를 부여하려 할 때."""


def validate_taxonomy_code(code: str) -> str:
    """택소노미에 없는 코드는 거부한다. 자유 텍스트 금지 (PRD F-04-1)."""
    valid = set(CODES.code_map(C.CODE_EXPERTISE_L1)) | set(CODES.code_map(C.CODE_EXPERTISE_L2))
    if code not in valid:
        raise ValueError(f"택소노미에 없는 전문분야 코드입니다: {code}")
    return code


def build(
    person_id: int,
    taxonomy_code: str,
    evidence_snippet: str,
    source_id: int,
    *,
    level: str = "중",
    confidence: str = "중",
    evidence_count: int = 1,
    is_primary: bool = False,
) -> Expertise:
    """Expertise 생성의 유일한 통로. 여기를 우회해 생성하지 말 것."""
    validate_taxonomy_code(taxonomy_code)
    if not evidence_snippet or not evidence_snippet.strip():
        raise MissingEvidenceError(
            f"근거 스니펫 없이 전문분야를 부여할 수 없습니다 "
            f"(person_id={person_id}, code={taxonomy_code}). PRD F-04-2"
        )
    if not source_id:
        raise MissingEvidenceError("출처 없이 전문분야를 저장할 수 없습니다. PRD F-05-1")
    return Expertise(
        person_id=person_id,
        taxonomy_code=taxonomy_code,
        level=level,
        confidence=confidence,
        evidence_count=evidence_count,
        evidence_snippet=evidence_snippet.strip(),
        is_primary=is_primary,
        source_id=source_id,
    )


def classify(person_id: int) -> list[Expertise]:  # pragma: no cover - 2단계 구현
    raise NotImplementedError(
        "자동 분류는 2단계(D)에서 구현합니다. 규칙 사전 → LLM 순으로 적용하고, "
        "근거 스니펫이 없는 결과는 build() 가 거부합니다."
    )
