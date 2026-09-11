"""내보내기용 데이터 조립 (PRD F-02-3, F-07).

화면(pages/)이 아닌 곳에서 조립해 단위테스트할 수 있게 한다.
사실 항목의 출처 URL 을 반드시 함께 싣는다. 근거 없는 전문분야는 싣지 않는다.
"""

from __future__ import annotations

from core import codes as CODES
from core import constants as C
from core import expertise as EXP
from core import scoring
from core.screening import effective, worst
from data.repository import get_person_detail, get_persons


def _urls(detail, items) -> list[str]:
    out: list[str] = []
    for it in items:
        src = detail.sources.get(it.source_id)
        if src and src.url and src.url not in out:
            out.append(src.url)
    return out


def candidate_rows(person_ids: list[int], fit_by_id: dict[int, float | None] | None = None) -> list[dict]:
    """person_ids 순서(=검색 순위)를 그대로 유지한 행 목록."""
    fit_by_id = fit_by_id or {}
    rows: list[dict] = []
    for rank, pid in enumerate(person_ids, start=1):
        d = get_person_detail(pid)
        if d is None:
            continue
        p = d.person
        current = next((x for x in d.positions if x.is_current), None)
        exps = [e for e in EXP.displayable(d.expertises, d.sources) if e.is_primary][:3]
        cur_dirs = [x for x in d.directorships if x.is_current]
        status = worst([effective(s) for s in d.screenings])
        fit = fit_by_id.get(pid, scoring.fit_score(pid))
        age = p.age()
        rows.append(
            {
                "순위": rank,
                "성명": p.name_ko,
                "영문명": p.name_en or "",
                "성별": {"M": "남", "F": "여"}.get(p.gender, "-"),
                "나이": f"만 {age}세{'(추정)' if p.age_estimated_yn else ''}" if age else "-",
                "현재 직업": f"{current.org_name} {current.title}" if current else "-",
                "전문분야": ", ".join(CODES.label_of(C.CODE_EXPERTISE_L2, e.taxonomy_code) for e in exps) or "-",
                "타사 등기임원": ", ".join(x.company_name for x in cur_dirs) or "없음",
                "스크리닝": C.SCREEN_BADGE[status],
                "적합도": scoring.display(fit),
                "검수 상태": p.profile_status,
                "최종 갱신": p.updated_at.date().isoformat() if p.updated_at else "-",
                "출처 URL": "\n".join(_urls(d, ([current] if current else []) + cur_dirs + exps)) or "-",
            }
        )
    return rows


def profile_statuses(person_ids: list[int]) -> list[str]:
    """출력 게이트 판정용 (reports.builder.check_export)."""
    return [p.profile_status for p in get_persons(person_ids)]
