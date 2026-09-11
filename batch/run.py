"""배치 실행기 (PRD F-09-8).

수집·분석처럼 무거운 작업은 Streamlit 프로세스 밖에서 실행한다. 화면은 AuditLog(entity='batch')에
남은 시작·종료 기록으로 진행 상태만 조회한다.

사용법
    python -m batch.run analyze     # 전문분야 분류 → 스크리닝 → 적합도 (순서 중요)
    python -m batch.run classify | screen | score
"""

from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv

JOBS = ("analyze", "classify", "screen", "score")


def _log(action: str, detail: str) -> None:
    from core.audit import log_change

    log_change(None, "batch", action, detail=detail)


def classify() -> int:
    from core import expertise

    return expertise.classify_all()


def screen() -> dict[str, int]:
    from core import screening

    return screening.evaluate_all()


def score() -> int:
    from core import scoring

    return scoring.score_all()


def analyze() -> dict:
    """분류가 먼저다: 스크리닝 R-07 과 적합도 스킬갭이 전문분야를 사용한다."""
    return {"classified": classify(), "screening": screen(), "scored": score()}


def run(job: str) -> dict:
    from data.session import init_db

    init_db()
    started = time.monotonic()
    _log("start", job)
    try:
        if job == "analyze":
            result = analyze()
        elif job == "classify":
            result = {"classified": classify()}
        elif job == "screen":
            result = {"screening": screen()}
        elif job == "score":
            result = {"scored": score()}
        else:
            raise ValueError(f"알 수 없는 작업입니다: {job}")
    except Exception as exc:
        _log("fail", f"{job}: {type(exc).__name__}")
        raise
    _log("finish", f"{job}: {result} ({time.monotonic() - started:.1f}s)")
    return result


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="독립이사 후보자 POOL 배치")
    parser.add_argument("job", choices=JOBS)
    args = parser.parse_args(argv)
    result = run(args.job)
    print(f"[batch] {args.job} 완료: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
