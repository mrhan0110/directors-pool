"""core/ui/components.py AppTest 하니스. pytest 가 직접 수집하지 않는다(파일명이 test_ 로 시작하지 않음)."""

from __future__ import annotations

from core import constants as C
from core.ui import components as UI

UI.page_header("헤더 테스트")
UI.confidential_banner("대외비 테스트 문구")
UI.status_badge(C.SCREEN_FAIL)
UI.status_badge(C.SCREEN_WARN)
UI.status_badge(C.SCREEN_PASS)
UI.status_badge(C.SCREEN_INFO)
UI.metric_card("등록 후보", "10명")
UI.candidate_card(
    "가상001 김서연", subtitle="가상전자 · 사외이사",
    badges=[(C.SCREEN_WARN, None)], meta=["잔여임기 3개월"],
)
UI.term_gauge(3, 6, "3개월 남음")
UI.term_gauge(-1, 6, "만료")
UI.term_gauge(None, 6, "임기 미상")
UI.result_count_banner(0, 0, None)
UI.result_count_banner(50, 50, None)
UI.result_count_banner(500, 100, "system")
UI.result_count_banner(80, 50, "viewer")


class _FakeSource:
    source_tier = "A"
    url = "https://dart.example.com/x"
    quote_snippet = "근거 인용"

    def citation(self) -> str:
        return "[출처] 테스트, 문서, 2026-01-01, url (수집일 2026-01-01)"


UI.source_popover(_FakeSource())
UI.source_popover(_FakeSource(), outdated=True)
UI.source_popover(None)
