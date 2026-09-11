# 작업 진행 상황 (이어하기용)

> **새 세션은 이 파일부터 읽는다.** PRD·코드 전체를 다시 분석하지 말고 `▶ 다음 작업`부터 바로 실행한다.
> 필요한 PRD 절만 해당 부분을 찾아 읽는다(`Grep`으로 요구사항 ID 검색).
> 작업 단위가 끝날 때마다: 테스트 통과 → 이 파일 갱신(체크·다음 작업·메모) → `git commit`.

## 이어하기 절차 (중단 후 재시작 시)

1. `git status` / `git diff --stat` — 마지막 커밋 이후 반쯤 된 변경이 있는지 확인
2. 변경이 있으면 `▶ 다음 작업`의 단위를 이어서 완성(되돌릴 필요 없음). 망가졌으면 `git checkout -- <파일>`
3. 테스트: `.\.venv\Scripts\python.exe -m pytest -q -p no:logging`
4. 모델(`data/models.py`)을 바꿨으면 개발 DB 재생성: `.\.venv\Scripts\python.exe -c "from data import seed; seed.run(reset=True)"`

## 현재 상태

- 1단계: ✅ 완료 (커밋 `1단계 완료`)
- 2단계: ✅ 완료 (2-1 ~ 2-14, DoD 검증 통과)
- 3단계: ✅ 완료 (3-1 ~ 3-7, DoD 검증 통과)
- 4단계: ⏳ 착수 전 — `PROMPTS_단계별_개발.md`의 4단계 정의부터 읽을 것

## ▶ 다음 작업

**3단계(UI 디자인) 전체 완료.** 다음은 `PROMPTS_단계별_개발.md`의 4단계(PRD 부합성 및 버그 검토)다.
착수 전 4단계 정의를 먼저 읽을 것(임의로 시작하지 않는다). 4단계에서 가장 먼저 처리할 것:
아래 "3-7 DoD 검증 결과"의 미해결 기능 버그(비교 화면 적합도 미연결).

### 3단계 작업 단위 체크리스트

- [x] 3-1 전역 스타일: `.streamlit/config.toml` 테마 확정, `core/ui/style.py`(CSS 한 곳 주입), app.py 에서 1회 주입
- [x] 3-2 재사용 컴포넌트 `core/ui/components.py`: status_badge/source_popover/metric_card/candidate_card/term_gauge/confidential_banner/result_count_banner
- [x] 3-3 S-01 대시보드 + S-02 검색: 배너·배지 컴포넌트 적용, 성별·연령 분포 차트(Altair, `core/ui/charts.py`)
- [x] 3-4 S-04 상세: 출처를 expander→popover 로, 요약헤더 정리, 잔여임기 게이지, 경력 타임라인 차트 + 평판 논조 추이 차트
- [x] 3-5 S-03 비교(4열 그리드+차이값 강조) + S-05 POOL 칸반(상태별 컬럼·색·카드) + S-06 검수 미처리 색 신호
- [x] 3-6 S-07 리포트 + S-08 관리자 + S-09 공유관리 표 다듬기, S-00 로그인 다듬기(중앙 열 정렬)
- [x] 3-7 DoD 검증(전 화면 통일 테마·1280px 무가로스크롤·스타일 코드 core/ui/ 집중) + 발견된 기능 버그 목록 정리 + 커밋

### 3-7 DoD 검증 결과 (2026-09-11)

1. 전 9개 화면(로그인·대시보드·검색·상세·비교·POOL·검수·리포트·관리자·공유관리)이 `core/ui/style.py`
   한 곳의 테마를 공유한다(app.py 가 최초 1회 주입).
2. 결격(🔴)·오버보딩·임기임박(🟡/🔴)·미검수(⚪)·결과 절단(amber 배너)이 색으로 즉시 구분된다
   (스크린샷으로 확인).
3. 상세 화면의 모든 사실 항목 옆에 출처 팝오버가 있다(F-05-1·2).
4. Playwright 로 1280×900 뷰포트에서 9개 화면 전부 `document.documentElement.scrollWidth`
   ≤ `clientWidth` 확인(가로 스크롤 없음). 스크립트: 스크래치패드 `pw_scrollcheck.py`.
5. `pages/*.py` 에 `<style>` 정의나 하드코딩된 hex 색상 없음(grep 확인) — 인라인 `style=` 는
   전부 `core/ui/style.py` 의 CSS 변수(`var(--pool-*)`)만 참조한다.

**발견했지만 고치지 않은 기능 이슈** (3단계 지시대로 목록만 남기고 수정하지 않음 — 4단계에서 처리):
- `pages/3_후보_비교.py` 의 '적합도' 행이 항상 `scoring.NOT_IMPLEMENTED_LABEL` 을 표시한다.
  상세 화면(`pages/2_후보_상세.py`)은 `scoring.get(person_id)` 로 실제 기본점수를 보여주는데
  비교 화면만 연결이 안 되어 있다. 기능 미완성으로 보인다.

### 3단계 참고
- Playwright: `.venv`에 설치됨(`pip install playwright` + `playwright install chromium`). 서버는 `Start-Process`로 백그라운드
  실행(`streamlit_out.log`/`streamlit_err.log`), 스크린샷은 스크래치패드 `pw_shot.py <출력.png> [--email] [--nav]`.
- 화면 렌더 테스트(`tests/test_pages_render.py`)는 문구·구조를 일부 단언하므로 UI 변경 후 반드시 재확인.

**(참고) 2단계(기능 추가) 전체 완료 — 아래는 완료된 2단계 기록.**

### 2-14 DoD 검증 결과 (2026-09-11)

1. **커버리지**: `core`+`data`+`batch`+`collectors` 93% (목표 70% 이상 충족). `collectors/dart.py`·`news.py`·`web.py`의
   실제 API 호출부만 0%— 키가 없어 의도적으로 미구현(README "알려진 제약" 참고). 재현: CLAUDE.md 명령어 절 참고.
2. **PRD §13 인수기준 매핑** (1~9·15~17. 10~14는 §J 작업인 2-11에서 이미 검증 — test_pages_guard/test_viewer_pages/test_sharing):
   - #1 드롭다운 전용 검색: `pages/1_후보_검색.py`에 `st.text_input` 없음 — `test_pages_render.py`가 검색 위젯 종류를 검증
   - #2 목록에 성별·나이·현재직업·겸직수·스크리닝 표시: `core/search.py SearchRow` + `test_search_features.py`
   - #3 최근10년+임원급, 초과분 자동제외: `core/career.py` + `test_career.py`(경계값 포함)
   - #4 잔여임기 O년O개월: `Directorship.remaining_term_months` + `test_directorship_term.py`
   - #5 전 사실항목 출처(무작위 20인 검사 0건): 스키마에서 `source_id NOT NULL`로 원천 차단(전수 검사가 표본검사보다 강함) +
     `data.repository.source_integrity_report()` + `test_invariants.py::test_no_fact_without_source`
   - #6 화이트리스트 밖 출처 유입 차단: `collectors/base.py assert_source_allowed` + `test_ingest.py::test_collected_fact_rejects_blocked_domain`
   - #7 결격 후보 하단 분리: `core/search.py` 정렬(SCREEN_ORDER) — 2-4 설계결정 §F 참고
   - #8 검수 미완료 PDF 차단: `reports/builder.check_export` + `test_report_gate.py` + `test_pages_render.py`(버튼 비활성 확인)
   - #9 팩트 오류율 3% 이하: **자동화 대상 아님.** 합성 더미데이터 단계라 표본 오류율 측정 자체가 무의미하다.
     운영 전환 후 실제 데이터로 사무국·검수자가 수행해야 하는 인적 프로세스로 남긴다
   - #15 상위 N명 + `전체 매칭 N명 중 상위 M명 표시`: `core/search.py resolve_limit`/`shown` + `test_search_limit.py`
   - #16 `전체` 선택 시 시스템 상한(기본 500) 초과 안내: `SET_RESULT_LIMIT_SYSTEM_MAX` + `test_search_limit.py`
   - #17 100명 조회 3초 이내: 개발 DB(SQLite, 200명 시드)에서 `core.search.search({}, "N100", role=None)` 3회 실측
     0.016~0.065초로 여유 있게 충족. **주의**: 운영 규모(PostgreSQL, 수천 명)에서는 재측정 필요 — 3단계 이후 실데이터
     투입 시 다시 확인할 것
3. **README.md·CLAUDE.md 갱신 완료**: 2단계 완료 상태, 배치 서브커맨드, 알려진 제약(라이브 수집기 미구현·SSO 미연동·PRD §14
   미결 16건은 AppSetting 기본값으로 처리) 반영
4. 전체 테스트 300여 건 통과 확인 후 이 커밋으로 2단계 마무리

**(완료) 2-13 관리자 화면** (F-01-7). `core/codes.py`에 `all_categories/load_all/create_code/update_code`(코드는 삭제하지 않고 비활성화만, 변경 시 AuditLog `code` 엔티티에 `카테고리/코드` 형식으로 기록), `core/settings.list_all`(설명·법령근거 포함 전체 조회), `core/audit.history_of(entity, prefix)`(코드·설정 변경 이력 공용 조회), `data/repository.recent_access_logs`. `pages/7_관리자.py`를 실제 CRUD 폼으로 교체(드롭다운 코드 탭: 카테고리 선택 → 기존 코드 수정 폼 + 신규 추가 폼 + 변경이력 expander / 운영 파라미터 탭: 값 수정 폼 + 변경이력). 페이지에서 직접 SQL을 쓰던 기존 코드(탭 4개)도 이번에 repository/core 경유로 정리했다(계층 규칙 준수). `tests/test_admin.py` 10건(코드 CRUD 유효성·중복 거부·noop 무이력, 설정 이력, AppTest로 폼 제출까지 실제 클릭 경로 검증). 전체 테스트 299개 통과.

**(완료) 2-12 G 수집.** `core/ingest.py` 신설 — 더미/실제 공용 적재 파이프라인:
- 인물 식별 `resolve_person`/`get_or_create_person`: 이름 완전일치 후보를 생년월(±0.5)+소속이력 겹침(±0.5)+성별(+0.1)로 채점, `identity.auto_merge_threshold`(기본 0.8) 미만이면 **자동 결합하지 않고** `ReviewQueue(QUEUE_IDENTITY)`로 보낸다. 이름이 아예 겹치지 않으면 `PersonBlocklist` 확인 후 신규 생성.
- 사실 적재 `ingest_fact`(position/directorship/reputation/achievement 공용, 자연키는 `MATCH_KEYS`): 기존 행이 `manually_edited=True`면 `core.review.EDITABLE` 교집합 필드만 `ReviewQueue(QUEUE_CONFLICT)`로 큐잉(payload 형식을 `core.review.resolve_alert`가 그대로 처리하도록 맞춤 — 검수 화면에서 그대로 승인/거부 가능). 아니면 상위 신뢰등급(A>B>C, 동급이면 최신 발행일)을 채택하고 하위 값은 `FieldConflict`로 병기(F-05-3). `ingest_industry`는 PersonIndustry 존재만 사실이므로 최초 1건만 적재.
- `purge_expired`(retention_until 경과 자동 파기, 부속 테이블도 함께 정리 — cascade 안 걸린 PersonIndustry/PersonScore/ConsiderationCheck/ReviewLog/ExpertiseHistory/PoolMember 수동 삭제), `delete_person_request`(즉시 파기 + `PersonBlocklist` 등록으로 재수집 차단, §5.2).
- `check_urls(fetcher=None)`(F-05-5, 기본은 `urllib` HEAD 요청이지만 테스트는 fetcher를 주입해 네트워크 없이 검증), `save_snapshot`(F-05-6, `storage/snapshots/<subdir>/<file>`에 저장하고 상대경로 반환 — `Source.snapshot_path`에 넣는다).
- `run_dummy_collection()`: 위 파이프라인 전체(신규 생성·동일인 매칭·동명이인 큐잉·차단·등급충돌·검수보호)를 실제와 같은 경로로 통과시키는 시나리오. `batch/run.py collect`(DATA_MODE=dummy 기본)가 이를 호출. `batch/run.py`에 `url-check`·`purge` 서브커맨드도 추가.
- 테스트: `tests/test_ingest.py` 14건(식별·충돌·검수보호·파기·차단·URL점검·스냅샷·배치 CLI 로그).
- **의도적으로 미룬 부분**: `collectors/dart.py`·`news.py`·`web.py`의 실제 라이브 API 호출부는 여전히 `NotImplementedError`(1단계 상태 그대로)다. 실제 DART/뉴스 API 키가 없어 이 세션에서 검증할 수 없고, 잘못 구현하면 조용히 깨진 채로 남을 위험이 커서 보수적으로 미뤘다. 실제 구현 시 파싱 결과를 `core.ingest.ingest_fact`/`ingest_industry`/`get_or_create_person`에 그대로 태우면 된다(파이프라인은 이미 완성). API 키 발급 전까지는 `batch.run collect`가 더미 경로만 탄다(§14 미결과 무관, 키 문제).

**(참고) 2-10 커밋 → 2-11 J 인증·공유** (§J).
- 2-10(검증 완료, 커밋 전이면 먼저 커밋): reports/pdf.py reports/builder.py pages/6_리포트.py core/state.py tests/test_pdf.py tests/test_pages_render.py PROGRESS.md. 샘플 PDF 육안 확인 완료(한글·워터마크·각주·2면). POOL PDF는 리포트 화면 POOL 탭에서 제공(POOL 화면 버튼 없음).
- 2-11 작성됨: `core/sharing.py`(issue_link/revoke/verify_token/active_links_for/list_links/status_of/access_history, 토큰 sha256만 저장, 수신자 활성 계정 필수, 만료 상한 설정), `core/access.py`(allowed_pool_ids/allowed_person_ids/can_view_person/filter_person_options — 뷰어만 제한, 매 요청 DB 재계산), `core/auth.refresh_user`, `tests/helpers.py`(user_for(role)), `tests/test_sharing.py`.
- 2-11 남은 것: ① `guard.require`에 `refresh_user`(비활성·만료·역할변경 즉시 반영) + `confidential_notice`에 열람자·일시 스탬프 ② `app.py`: refresh + `?share=` 토큰(로그인 전엔 보관만, 로그인 후 verify_token → 실패 사유 표시, 쿼리파라미터 제거, 성공 시 POOL 화면) ③ 대시보드: 뷰어는 공유받은 POOL만 ④ 상세·POOL 화면에 access 필터(범위 밖 후보·POOL 차단) ⑤ 공유 관리 화면(S-09: 발급 폼·링크 1회 표시·상태(유효/만료 임박/만료/회수)·회수·접속 이력) ⑥ 시드에 viewer@example.com → POOL1 공유 1건 ⑦ **테스트의 사용자 id를 역할별 실제 계정으로 교체**(`tests/helpers.user_for`) — refresh_user 도입 시 user_id=1(담당자)에 관리자 역할을 넣던 test_pages_render/test_pages_guard가 깨짐 ⑧ 뷰어 화면 테스트(범위 밖 후보 차단, 회수 즉시 차단).
- 2-8 완료 메모: 상세 화면 헬퍼 = `SRC.FreshnessPolicy/is_outdated/conflicts_of/conflict_index`, `CS.evaluate/get_checks/save_check`, `REP.signals/status_parts`, `career.remaining_label`. 권한 = `can_edit_pool`(담당·국장·관리), `can_review`(뷰어 제외), `can_override_screening`(법무·관리).

**(완료) 2-7. B 결과 목록 액션 + XLSX** (§B). 2-7 커밋 대상: core/search.py core/auth.py core/state.py pages/1_후보_검색.py core/pools.py reports/xlsx.py reports/exports.py tests/test_pools.py tests/test_exports.py tests/test_search_features.py tests/test_pages_render.py PROGRESS.md. 이미 작성됨(미커밋 가능): `core/pools.py`(POOL CRUD·상태전이·코멘트·타임라인·동시수정 거부), `reports/xlsx.py`(build_table_xlsx, 워터마크), `reports/exports.py`(candidate_rows: 순위·출처 URL), 테스트 `tests/test_pools.py`, `tests/test_exports.py`. 남은 것: `core/search.py`에 `search_ranked()`(id, 적합도) 추가 → 검색 화면 결과표를 `st.dataframe(on_select="rerun", selection_mode="multi-row")`로 바꾸고 선택 후보 [상세] [비교함] [POOL 추가(기존/신규: 명칭·목적·대상 직위·메모)], XLSX 다운로드(상위 N명 전체, `check_export` 게이트 — 미검수 포함 시 비활성+사유, 다운로드 시 AccessLog export).

**(완료) 2-6. A 검색 core + 필터 화면** (§A). core: `search(f, limit_code, role, page=1)` 페이지네이션(SearchResult에 page/page_size/page_count, `shown`=min(N,전체)), `search_ids()`(상위 N명 id — 내보내기·POOL 저장용), `core/presets.py`(목록/저장(이름 upsert)/삭제(소유자 확인)), `core/preferences.py`(get/set, 키 `search.limit_code`). 화면(`pages/1_후보_검색.py`): 건수 배지(`option_counts`를 `st.cache_data(ttl=60)`, 필터 JSON 키), 조건 칩 ✕ 해제, 프리셋 저장·불러오기, 최근 인원수 영속, 페이지 이동, 100명↑ 지연 안내+spinner, 적합도 상시 문구. `tests/test_search_limit.py`의 `shown == len(rows)` 단언은 페이지네이션에 맞게 수정.
- 2-5 메모: 시드는 마지막에 `batch.run.run("analyze")` 호출(200명 ≈ 28초). 배치 CLI `python -m batch.run analyze|classify|screen|score`, AuditLog entity=`batch` start/finish/fail. **스크리닝 기관명 매칭은 정규화 후 정확 일치만**(부분 포함 매칭이 대주주 재단을 자사로 오판한 버그 수정).
- 2-4 메모: 점수 API = `SC.Weights/ScoreContext.load`, `base_score`, `store/score_all/get/fit_score/breakdowns_in`, SQL `fit_expr(f)`, 표시 `display()/describe()`, 상시 문구 `SC.DISCLAIMER`. SearchRow에 `fit_score`(None=미산출), `fit_basis` 추가. **정렬: 결격만 하단 분리(🟡는 분리 안 함)**, 정렬 끝에 person_id로 안정 정렬.
- 2-3 메모: 전문분야 API = `EXP.classify_evidence/evidence_from_detail/classify/store/classify_all`, `confirm/set_primary/remove/history_of`, 출력 가드 `EXP.displayable(expertises, sources)` — **상세·비교·리포트 화면은 반드시 이 가드를 거칠 것**. 현 seed의 duties가 "(더미) 주요 담당 업무"라 분류 근거가 빈약 → 2-5에서 키워드 포함 담당업무 문구로 교체.
- 2-2 메모: 스크리닝 API = `OrgContext.load()`, `evaluate_input/evaluate/evaluate_and_store/evaluate_all`, `set_override`, `effective`, `worst`. 현 더미데이터상 R-01·R-02·R-05 전원 pass → **2-5 시드에 자사·계열사·대주주·장기재직·`형사 판결` 케이스 추가 필요**.

## 2단계 작업 단위 체크리스트

각 단위 = 구현 + 테스트 + 커밋. 순서대로 진행.

- [x] 2-1 모델·설정 확장 (신규 테이블/컬럼, AppSetting 키, SCREEN_INFO) — §M
- [x] 2-2 E 스크리닝 룰엔진 R-01~R-08 (`core/screening.py`) — §E
- [x] 2-3 D 전문분야 자동 분류 (`core/expertise_rules.py`, `core/expertise.py`) — §D
- [x] 2-4 F 적합도 점수 (`core/scoring.py`, PersonScore) — §F
- [x] 2-5 시드 재작성: 엔진으로 스크리닝·분류·점수 산출, 자사/충돌/수동검수 케이스 포함 + `batch/run.py`
- [x] 2-6 A 검색 core+화면: 건수 배지, 칩 해제, 프리셋, 최근 인원수 사용자별 저장, 페이지네이션 — §A
- [x] 2-7 B 결과 목록: 전체 컬럼, 행 선택→상세/POOL 추가/비교, XLSX 내보내기 — §B
- [x] 2-8 C 상세: 전 섹션, 출처 충돌(대체 정보), 구 정보 배지, 평판 정량, 18개 고려사항 체크리스트 — §C
- [x] 2-9 H POOL 관리(CRUD·상태 전이·사유·타임라인) + 검수(3분할·승인/수정/삭제·ReviewLog·충돌 알림) — §H
- [x] 2-10 I 리포트: 사추위 2페이지 PDF(부록 A·B, 워터마크) + POOL PDF/XLSX — §I
- [x] 2-11 J 인증·공유: OIDC 인터페이스, 외부뷰어 POOL 범위 제한, 공유 링크 발급/회수/검증, 로그 — §J
- [x] 2-12 G 수집: 더미/실제 모드, DART 클라이언트, 뉴스·웹, 인물 식별(동명이인 큐), 스냅샷, URL 점검, 보관기간 파기 — §G (DART/뉴스/웹 실제 API 호출부는 키 없어 미구현 상태 유지, 적재 파이프라인은 완성)
- [x] 2-13 관리자: 코드 추가·수정·이력, 설정값 수정·이력 (F-01-7)
- [x] 2-14 DoD 검증: 커버리지 ≥70%(93%), §13 인수기준 1~9·15~17 매핑, 100명 조회 3초(0.02~0.07초), README·CLAUDE.md 갱신

## 설계 결정 (재분석 없이 이대로 구현)

### §M 모델·설정
- `SCREEN_INFO="info"` 추가(R-07·R-08용, 대표 상태 계산에서 pass 취급). 배지 `ℹ️ 참고`.
- 신규 테이블: `PersonScore`(person_id PK, base_score, breakdown JSON, computed_at) / `SearchPreset`(user_id, name, filters JSON, limit_code) / `UserPreference`(user_id, key, value) / `ConsiderationCheck`(person_id, item_no, status, comment, attachment_name, attachment_bytes?, updated_by, updated_at) / `FieldConflict`(person_id, entity, entity_id, field, adopted_value, adopted_source_id, alt_value, alt_source_id) / `ExpertiseHistory`(expertise 수정·확정 이력) / `PoolEvent`(pool_id, person_id, event, comment, user_id, at) / `ViewerPoolGrant`는 만들지 않음 → 외부뷰어 범위는 유효한 ShareLink(recipient_email=본인)로 판정 / `PersonBlocklist`(name_ko, birth_year, reason) 재수집 차단
- 사실 테이블에 `manually_edited` bool 추가(F-08-4: 자동 갱신 시 덮어쓰지 않고 ReviewQueue `충돌 알림`)
- AppSetting 추가 키: 자사명 `org.own_company`, 계열사 `org.affiliates`(콤마), 최대주주·특수관계 `org.major_shareholders`, 이해상충 기관 `org.conflict_orgs`, 자사 자산총액 `org.total_assets_krw`, 성별 규정 자산 기준 `rule.gender_rule_asset_threshold_krw`, 자사 이사회 여성 수 `org.board_female_count`, 이사회 스킬 공백 `org.board_skill_gaps`(택소노미 코드 콤마), 점수 가중치 `score.weight.*`(40/20/15/15/10), 언론 최신성 `source.news_fresh_years`(3), 홈페이지 최신성 `source.web_fresh_days`(365), 동명이인 자동결합 임계 `identity.auto_merge_threshold`
- 스키마 변경 후 개발 DB는 reset 재생성(마이그레이션 도구 없음, 운영 전환 시 Alembic 검토)

### §E 스크리닝 (임계값은 전부 settings)
- R-01: 자사·계열사 현직 상근 → fail / 냉각기간(`rule.cooling_off_years`) 내 재직 → fail
- R-02: 소속이 `org.major_shareholders` 목록 → fail
- R-03: 현직·냉각기간 내 소속이 `org.conflict_orgs` → warn
- R-04: 현 상장사 겸직 > 한도 → fail, = 한도 → warn(자사 선임 시 한도 도달)
- R-05: 자사 재직 합산 > `rule.tenure_limit_years` 또는 계열 합산 > `rule.affiliate_tenure_limit_years` → fail
- R-06: 확인된 부정(법적 분쟁/규제 제재) 상태 `확정` → fail, `진행중` → warn. **미확인 건은 판정 미반영**(사유에 "미확인 보도 N건" 기록)
- R-07: 공인회계사/CFA 자격, EXP_FIN·EXP_AUD 전문분야, ACCT_*·CORP_CFO 경력 중 하나 → info "충족" / 아니면 info "미충족"
- R-08: 자산총액 ≥ 기준 & 자사 이사회 여성 0 & 후보 남성 → info 다양성 경고
- 근거 불충분하면 fail 대신 warn. `reviewer_override` 있는 행은 재평가 시 보존. 사유 문자열에 근거 데이터 포함

### §D 전문분야
- 근거 단위: 경력(직위·기관·담당업무), 업적, 출처 인용문. 각 근거는 (텍스트, source_id, 날짜, tier)
- 키워드 사전 `core/expertise_rules.py`: 택소노미 중분류 코드 → 키워드 목록
- 점수 = Σ 최신성가중(≤5년 1.0 / ≤10년 0.6 / 초과 0.3) × tier가중(A1.0/B0.8/C0.5)
- 상위 3 = is_primary, 나머지 보조. 신뢰도: 점수·근거건수 기준 상/중/하
- evidence_snippet = 매칭된 원문 인용, source_id 필수 → `build()` 경유(가드)
- LLM 분류: `EXPERTISE_LLM_ENABLED` 플래그, 인터페이스만(기본 off, §14-3 미결)
- `confirmed_by_user_yn=True`는 재분류가 덮어쓰지 않음. 담당자 수정·확정은 ExpertiseHistory 기록

### §F 적합도
- 저장: PersonScore.base_score = 스킬갭(20) + 경력수준(15) + 가용성(15) − 리스크(10). 배치에서 산출
- 검색 시 SQL로 전문분야 매칭(40) = 가중치 × (선택 전문분야 중 보유 수 / 선택 수). **미선택이면 전원 0**(스킬갭과 이중계산 방지 — 2-4에서 변경)
- FIT 정렬 = base + 매칭식, SQL ORDER BY + LIMIT 유지(F-09-5-1). 결격 하단 분리는 그대로
- 미확인 평판은 리스크에 미반영. 화면 상시 문구 `scoring.DISCLAIMER`

### §A 검색
- 건수 배지: `option_counts` 결과를 `@st.cache_data(ttl=60)` (필터 dict 해시 키, 역할 무관한 공용 데이터)
- 칩: 선택 조건별 `✕` 버튼으로 개별 해제
- 프리셋: SearchPreset에 필터+limit_code 저장/불러오기(불러오면 위젯 키 초기화)
- 최근 조회 인원수: UserPreference(`search.limit_code`)에 영속 저장
- 페이지네이션: page_size(설정)와 N 별개. search(page=) → OFFSET, 표시 수 = min(N, total)

### §B 결과
- `st.dataframe(on_select="rerun", selection_mode="multi-row")`로 선택 → [상세] [POOL 추가] [비교함]
- XLSX: `reports/xlsx.py` (openpyxl). 시트1 목록+출처 URL, 시트2 조회 조건·인원수·일시·열람자. 
- **해석 결정(사용자 확인 필요로 보고할 것)**: F-09-9에 따라 목록에 미검수 후보가 있으면 XLSX 버튼 비활성(보수적). 

### §C 상세
- 출처는 값마다 `st.expander("출처 보기")`(F-09-6). 구 정보 배지(F-05-4)
- FieldConflict 있으면 채택값 옆 `대체 정보: 값 (출처 등급)` 병기
- 평판 정량: 연도별·논조별 건수(Reputation 기준), 거버넌스 이력 데이터 없으면 "수집된 이력 없음"
- 18개 고려사항: `core/considerations.py`에 자동 판정(1,3,4,5,6,7,8,9,15,18 등), 수기 항목은 ConsiderationCheck 입력(상태·코멘트·첨부)

### §H POOL·검수
- 제외·보류 전이 시 사유 필수, PoolEvent 타임라인
- 검수: 항목별 승인/수정/삭제 → ReviewLog + AuditLog, 수정 시 manually_edited=True, 전 항목 처리 후 `검수완료`

### §I 리포트
- ReportLab, 한글 폰트: 환경변수 `PDF_FONT_PATH` → Windows `malgun.ttf` → 내장 CID `HYGothic-Medium` 폴백
- 2페이지, 항목별 출처 각주(부록 B `Source.citation()`), 모든 페이지 워터마크(열람자·일시)+대외비 고지
- 게이트는 `reports.builder.check_export` 재사용. 다운로드 시 AccessLog `export`

### §J 인증·공유
- 토큰: `secrets.token_urlsafe(32)`, DB엔 sha256만. 링크 `?share=<token>` → 로그인 후 이메일 일치·미만료·미회수 검증
- 외부뷰어 접근 범위 = 본인 이메일로 발급된 유효 ShareLink의 POOL 구성원. **매 요청 DB 재검증**(세션 신뢰 금지)
- 공유 발급: 수신자·목적·범위·만료일 필수, 만료 기본값 설정, 최대 기간 설정

### §G 수집
- `batch/run.py` CLI: `collect`, `screen`, `classify`, `score`, `url-check`, `purge` (Streamlit 밖)
- 더미 모드: 가짜 CollectedFact를 생성해 **실제와 같은 적재 파이프라인**(`core/ingest.py`) 통과
- 인물 식별: 이름+생년 일치+소속 이력 겹침 점수 → 임계 미만이면 ReviewQueue(자동 결합 금지)
- 충돌: 상위 tier 채택, 하위는 FieldConflict. manually_edited 필드는 덮어쓰지 않고 ReviewQueue

## 사용자 확인 필요 (작업은 보수적 기본값으로 진행)

- (예정) 목록 XLSX에 미검수 후보 포함 시 차단 여부 — 현재: 차단

## 작업 로그

- 2026-09-11: 1단계 마무리(렌더 테스트 수정, README), git 초기화, 이어하기 장치 구축
- 2026-09-11: 2-1 ~ 2-10 완료·커밋(테스트 269개 통과). 2-11 코드 작성 후 사용자 요청으로 중단 — WIP 커밋, 테스트 미실행
- 2026-09-11: 세션 재개. 개발 환경에 git·`.venv`가 없어 새로 구축(winget으로 git 설치, `python -m venv .venv` + requirements 설치). 우발적으로 삭제돼 있던 `.streamlit/config.toml`·`secrets.toml.example`(CORS/XSRF 설정 포함, 2-11 작업과 무관)을 `git checkout --`으로 복구. 2-11 WIP 전체 테스트 통과 확인(exit code 0) → 2-11 완료 처리
- 2026-09-11: 2-12 G 수집 구현·검증·커밋(테스트 289개 통과). `core/ingest.py` 신설(적재 파이프라인)
- 2026-09-11: 2-13 관리자 화면 구현·검증·커밋(테스트 299개 통과)
- 2026-09-11: 2-14 DoD 검증 완료(커버리지 93%, §13 인수기준 매핑, 100명 조회 3초 이내 실측, README·CLAUDE.md 갱신) → 2단계 전체 완료. 다음은 3단계
- 2026-09-11: 3단계(UI 디자인) 전체 완료(3-1~3-7). `core/ui/style.py`(전역 CSS 1곳)·`components.py`(배지·팝오버·게이지·배너 등)·`charts.py`(Altair) 신설, 9개 화면 전부 적용. 사용자 요청으로 Playwright(`.venv`에 설치) 로 매 단위 작업 후 실제 화면을 스크린샷해 확인. 1280px 무가로스크롤 검증 통과. 발견한 기능 버그 1건(비교 화면 적합도 미연결)은 수정하지 않고 4단계로 넘김. 전체 테스트 330여 건 통과
