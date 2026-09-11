# 4단계 검토 보고서 — PRD 부합성 및 버그 검토

- 작성일: 2026-09-11
- 대상: 커밋 `79dbbe9`까지(1~3단계 전체 구현분)
- 방법: PRD 원문 재독 + 실제 코드 열람(파일:라인 근거) + 기존 테스트 스위트(330여 건) 실행 결과 + Playwright 실측(1280px 스크롤, 로그인/역할 전환 재현) + 신규 재현 스크립트
- **이 문서는 검토 결과 보고이며, 어떤 코드도 수정하지 않았다.** 수정은 사용자 승인 후 별도로 진행한다.

---

## Part 1 — PRD 요구사항 추적 매트릭스

판정 기준: **충족** / **부분충족** / **미구현** / **요구사항과 다르게 구현** / **확인 불가**

### F-01 조건 검색

| ID | 내용 요약 | 상태 | 근거 파일:라인 | 비고 |
|---|---|---|---|---|
| F-01-1 | 전체가 기본값, 미선택 필터 제외 | 충족 | `pages/1_후보_검색.py:78`, `core/search.py:6` | |
| F-01-2 | 대분류→중분류 cascading | 충족 | `pages/1_후보_검색.py:119-123,174-192`, `core/codes.py:393-408`, `core/state.py:84-89` | |
| F-01-3 | 항목별 건수 배지 | 충족 | `pages/1_후보_검색.py:56-62`, `core/search.py:518` | `@st.cache_data(ttl=60)` |
| F-01-4 | 조건 칩 개별 해제 | 충족 | `pages/1_후보_검색.py:126-139,288-310` | |
| F-01-5 | 검색 프리셋 저장/재사용 | 충족 | `pages/1_후보_검색.py:210-239`, `core/presets.py`, `data/models.py:509-521` | |
| F-01-6 | 0건 시 조건 완화 제안 | 충족 | `pages/1_후보_검색.py:345-352`, `core/search.py:482-516` | |
| F-01-7 | 코드값 관리자 추가·수정 + 이력 | 충족 | `pages/7_관리자.py`(코드 탭), `core/codes.py:429-495`(create/update, 비활성화만) | 삭제 대신 비활성화 — 과거 데이터 보존 목적, 의도된 설계 |
| F-01-8 | 최대 조회 인원 수 전반 | 충족 | `pages/1_후보_검색.py:259-284`, `core/search.py:294-311`(SQL LIMIT), `core/preferences.py`(사용자별 기억), `core/settings.py`(시스템상한/역할별 상한) | 2-14에서 배너 문구·상한 로직 실측 완료 |

### F-02 검색 결과 목록

| ID | 내용 요약 | 상태 | 근거 파일:라인 | 비고 |
|---|---|---|---|---|
| F-02-1 | 최대 4명 비교 | 충족 | `pages/1_후보_검색.py:467-475`, `pages/3_후보_비교.py:23-27`(max_selections=4) | |
| F-02-2 | POOL 저장(명칭·목적·대상직위·메모) | 충족 | `pages/1_후보_검색.py:477-507`, `core/pools.py:60-87` | |
| F-02-3 | XLSX 내보내기(출처 URL 포함, 조건·인원·일시 동봉) | 충족 | `pages/1_후보_검색.py:511-549`, `reports/xlsx.py`, `reports/exports.py` | |
| F-02-4 | 배너 + 인원수 드롭다운 상단 배치 | 충족 | `pages/1_후보_검색.py:259-284,345` | |
| F-02-5 | N(조회 인원)과 페이지 크기 분리 | 충족 | `pages/1_후보_검색.py:439-453`, `core/search.py:294-311`, `core/settings.py:39`(SET_PAGE_SIZE) | |
| F-02-6 | 100명↑ 지연 안내 | 충족 | `pages/1_후보_검색.py:322-324` + `st.spinner` | |

### F-03 후보자 상세 프로파일

| ID | 내용 요약 | 상태 | 근거 파일:라인 | 비고 |
|---|---|---|---|---|
| F-03(1) 기본정보 | 성명·성별·나이·국적·학력·자격 | 충족 | `pages/2_후보_상세.py:191-211` | |
| F-03(2) 현재직업 | 소속·직위·상근·시작일·담당업무 | 충족 | `pages/2_후보_상세.py:213-229` | |
| F-03(3) 과거직업 10년/임원급 | 충족 | `core/career.py`(build_view), `pages/2_후보_상세.py:233-270`, `tests/test_career.py` | 경계값(정확히 10년) 테스트 존재 |
| F-03-1 | 잔여임기 O년O개월, 6개월 강조 | 충족 | `core/career.py:34`, `data/models.py:216-230`, `pages/2_후보_상세.py:280-296`, `tests/test_directorship_term.py` | 만료/미상/윤년 케이스 테스트됨 |
| F-03-2 | 오버보딩 경고(한도 초과) | 충족 | `pages/2_후보_상세.py:262-267`, `core/settings.py:57`(SET_CONCURRENT_LIMIT) | |
| F-03-3 | 이사회 출석률 표시 | 충족 | `pages/2_후보_상세.py:288-302` | |
| F-03-4 | 종료된 등기임원 이력 collapse | 충족 | `pages/2_후보_상세.py:304-320`(`st.expander`) | |
| F-03(5) 평판 | 정량신호·긍정/부정근거·거버넌스 | 부분충족 | `core/reputation.py`, `pages/2_후보_상세.py:322-351` | 정량신호·긍정/부정 근거는 충족. **거버넌스 이력(과거 반대·기권 의결, 주총 부결)은 하드코딩된 "수집된 이력 없음" 캡션만 있고 실제 데이터 모델·수집 경로가 없음**(`pages/2_후보_상세.py:351`) |
| F-03(6) 업적 | 정량지표+출처 | 충족 | `pages/2_후보_상세.py:355-361` | |
| F-03-5 | 고려사항 코멘트+첨부 | 충족 | `pages/2_후보_상세.py:387-404`, `core/considerations.py:171-`, `data/models.py:534-551`(첨부 bytes) | |
| F-03-6 | A4 2~3면 PDF, 출처 각주 | 충족 | `reports/pdf.py`(2면+PageBreak, 각주 Notes 클래스), `reports/builder.py:54-70` | 실물 PDF 육안 확인 기록 있음(PROGRESS.md 2-10) |
| F-03(7) 18개 고려사항 | 충족(자동 판정 가능한 항목만) | `core/considerations.py`(18개 전항목 정의) | 10·11·12·14·16·17번은 PRD상 "수기"로 명시된 항목이라 자동판정 없음 — 요구사항과 일치 |

### F-04 전문분야 자동 분류

| ID | 내용 요약 | 상태 | 근거 파일:라인 | 비고 |
|---|---|---|---|---|
| F-04-1 | 택소노미만 사용, 자유텍스트 금지 | 충족 | `core/expertise.py:50`(택소노미 밖 코드 거부) | |
| F-04-2 | 근거 없는 분류 금지 | 충족 | `core/expertise.py:75-78`, `data/models.py:248`(evidence_snippet NOT NULL) | 불변규칙 2로 스키마 레벨 강제 |
| F-04-3 | 신뢰도·근거건수 표시 | 충족 | `pages/2_후보_상세.py:143-146` | |
| F-04-4 | 수정·확정 + 이력 | 충족 | `pages/2_후보_상세.py:150-178`, `core/expertise.py:265,359`, `data/models.py:577-589`(ExpertiseHistory) | |
| 분류로직 3(최신성·신뢰도 가중) | 충족 | `core/expertise_rules.py`, `core/expertise.py`(가중합산 로직) | |
| 분류로직 4(상위3 대표) | 충족 | `core/expertise.py:27`(MAX_PRIMARY=3) | |

### F-05 데이터 수집 및 출처 관리

| ID | 내용 요약 | 상태 | 근거 파일:라인 | 비고 |
|---|---|---|---|---|
| F-05-1 | 출처 없는 값 저장·표출 금지 | 충족 | `data/models.py`(Position/Directorship/Expertise/Reputation/Achievement 전부 `source_id` NOT NULL FK), `collectors/base.py:34-37`(스니펫 없으면 예외), `data/repository.py:190-220`(source_integrity_report 전수검증, 항상 0 확인됨) | 스키마 레벨 강제라 우회 불가 |
| F-05-2 | 값 옆 [출처] 팝오버 | 충족 | `core/ui/components.py:39-56`(source_popover) | ⚠ 아래 F-09-6과 표현 불일치 있음(뒤에서 설명) |
| F-05-3 | 상위등급 채택 + 대체정보 병기 | 충족 | `core/sources.py:53-67`, `core/ingest.py:118-134`(자동 적재 시), `data/models.py:554-575`(FieldConflict), `pages/2_후보_상세.py:89-97`(conflict_note) | |
| F-05-4 | 최신성 기준별 구정보 배지 | 충족 | `core/sources.py:26-50`(공시 460일/언론 3년/홈페이지 365일, 전부 설정값) | |
| F-05-5 | URL 점검 + 재수집/스냅샷 | 부분충족 | `core/ingest.py:375-403`(check_urls), `batch/run.py`(url-check 서브커맨드) | 점검 자체는 동작. **"404 시 아카이브 스냅샷 또는 재수집을 수행"은 미구현** — 현재는 `url_alive_yn` 플래그만 갱신하고 끝, 자동 재수집·아카이브 연동 로직 없음 |
| F-05-6 | 원문 스냅샷 보관 | 부분충족 | `core/ingest.py:57-64`(save_snapshot, 실제 파일 저장+상대경로 반환, 테스트됨) | **실제 수집기(dart/news/web)가 미구현이라 이 함수를 호출하는 라이브 경로가 아직 없다.** 더미 시드는 snapshot_path 문자열만 채우고 실제 파일은 만들지 않음(`data/seed.py:147`) |

### F-06 적합도 점수

| 내용 | 상태 | 근거 | 비고 |
|---|---|---|---|
| 가중치 구성·설정화 | 충족 | `core/scoring.py:39-74`, `core/settings.py`(SET_W_*, 관리자 화면에서 수정 가능) | 기본 가중치 40/20/15/15/10 은 PRD §6.6 수치와 일치 |
| 결격 후보 하단 분리 | 충족 | `core/search.py:266-283`(fail_rank 정렬), `core/constants.py:43-44` | |
| 상시 문구 | 충족 | `core/scoring.py:29`(DISCLAIMER), 각 화면에서 `st.caption(scoring.DISCLAIMER)` | |

### F-07 POOL 관리

| 내용 | 상태 | 근거 | 비고 |
|---|---|---|---|
| POOL CRUD | 충족 | `core/pools.py:60-120`, `pages/4_POOL_관리.py` | |
| 후보 추가/제외, 사유 필수 | 충족 | `core/pools.py:161-188`(REASON_REQUIRED 검증) | |
| 상태 관리(6단계+보류/제외) | 충족 | `core/constants.py:88-98`, `core/pools.py:41-55`(allowed_transitions) | |
| 이력·코멘트 타임라인 | 충족 | `core/pools.py:191-230`, `data/models.py:592-607`(PoolEvent) | |
| POOL 리포트 PDF/XLSX | 충족 | `reports/builder.py:73-101`, `pages/4_POOL_관리.py:193-221` | |
| **동명이인 병합/분리 기능** | **미구현** | `core/ingest.py:262-310`(resolve_person 이 애매한 매칭을 `ReviewQueue(QUEUE_IDENTITY)`로 큐잉까지는 함) | **큐에 쌓인 동명이인 후보를 사람이 검토해 "병합" 또는 "분리 유지"를 확정하는 화면·API가 전혀 없다.** `pages/` 어디에도 `QUEUE_IDENTITY`를 다루는 코드가 없음(확인: grep 결과 전무). 즉 동명이인 자동 결합은 안전하게 막고 있지만(리스크 §11 대응은 절반 충족), 그 다음 단계인 "사람이 확정" 워크플로가 비어 있어 큐가 영구히 쌓이기만 한다 |

### F-08 검수 워크플로우

| ID | 내용 | 상태 | 근거 | 비고 |
|---|---|---|---|---|
| F-08-1 | 미검수 시 외부출력 차단 | 충족 | `reports/builder.py:26-37`(check_export, 화면 차단과 별개로 생성 함수 자체가 재검증) | 이중 방어 구조 확인됨 |
| F-08-2 | 3분할(자동값/원문근거/승인수정삭제) | 충족 | `pages/5_검수.py:88-142` | |
| F-08-3 | 검수자·일시·수정내역 로그 | 충족 | `data/models.py:368-381`(ReviewLog), `core/review.py:111-113` | |
| F-08-4 | 수정 항목 자동갱신 시 충돌알림 | 충족 | `core/ingest.py:160-176`, `core/review.py:245-277`(resolve_alert) | payload 스키마가 review.resolve_alert 와 정확히 일치하도록 설계되어 있음(`core/ingest.py:11`) |

### F-09 Streamlit 웹 배포 및 공유

| ID | 내용 | 상태 | 근거 | 비고 |
|---|---|---|---|---|
| F-09-1 | text_input 키워드검색 금지 | 충족 | `pages/1_후보_검색.py:3`(원칙 명시), 검색 조건 위젯 전부 select/multiselect | 텍스트 입력은 프리셋 이름·POOL 메모뿐이며 검색조건 아님 |
| F-09-2 | CodeMaster `@st.cache_data(ttl=600)` 캐싱 | **미구현** | `core/codes.py:393-408`(load_codes, 캐시 데코레이터 없음, 매 호출마다 DB 쿼리) | 전체 코드베이스에 `@st.cache_data` 사용처는 단 1곳(`pages/1_후보_검색.py:58`, ttl=60, 건수배지용)뿐이다. 드롭다운 로드 자체는 캐싱되지 않는다 |
| F-09-3 | 상위 변경 시 하위 초기화(세션) | 충족 | `pages/1_후보_검색.py:119-123`, `core/state.py:84-89` | |
| F-09-4 | 검색조건·페이지 상태 세션 유지 | 충족 | `core/state.py` 전반 | |
| F-09-5 | dataframe + LinkColumn | 충족(적용 범위 내) | `pages/2_후보_상세.py:110`(LinkColumn) | 검색 결과 **목록**에는 URL 컬럼 자체가 없음(PRD F-02 컬럼표에도 없어 요구사항 불일치 아님). URL이 실제 표에 나오는 곳(상세의 과거경력·등기임원 표)엔 전부 적용됨 |
| F-09-5-1 | SQL LIMIT + 별도 COUNT | 충족 | `core/search.py:288-333` | |
| F-09-6 | `st.expander("출처 보기")` | **요구사항과 다르게 구현** | `core/ui/components.py:39-56`(st.popover 사용) | 3단계에서 UX 개선 목적으로 expander→popover 전환. **PRD 자체가 F-05-2("팝오버로 표시")와 F-09-6("expander 안에 표시")가 서로 모순**된다 — 이 코드는 F-05-2 문구를 따랐다. 기능적으로는 F-05-2 요구(원문 링크+인용 스니펫 팝업 표시)를 더 잘 만족하므로 문제로 보지 않지만, PRD 문서 자체의 모순이니 Part 5에서 PRD 수정 대상으로 제안 |
| F-09-7 | 캐시 사용자 ID 포함 | 충족(범위 내) | `pages/1_후보_검색.py:56-62`(주석: 외부뷰어 접근 불가 페이지라 사용자 무관 캐시가 안전하다는 근거 명시) | 캐시 사용 자체가 거의 없어(F-09-2 참고) 이 요구사항이 실제로 걸리는 지점이 한 곳뿐 |
| F-09-8 | 무거운 작업 배치 분리 | 충족 | `batch/run.py`(analyze/classify/screen/score/collect/url-check/purge), Streamlit 프로세스와 완전 분리 | |
| F-09-9 | 검수완료+권한 시에만 다운로드 노출 | 충족 | `reports/builder.py:26-37`, `pages/1,4,6` 버튼 disabled 처리 | |
| F-09-10 | 익명 접근 차단, 인증 방식 | 충족(개발단계 mock) | `core/auth.py`(AuthProvider 인터페이스, MockAuthProvider/OIDCAuthProvider) | OIDC는 인터페이스만(3.5단계 예정), 현재 mock 인증에는 로그인 화면에 경고 문구 상시 노출(`app.py:60`) |
| F-09-11 | 역할별 렌더링 차단 + 페이지 재검증 | 충족 | `core/guard.py:22-62`(require, 매 페이지 최상단 호출), `core/auth.py:125-170` | `tests/test_pages_guard.py` 로 전 페이지 URL 직접 접근 테스트됨 |
| F-09-12 | 외부뷰어 격리 + 만료일 필수 | 충족 | `core/access.py`, `data/models.py:428`(expires_at), `core/auth.py:72-76` | |
| F-09-13 | 세션 유휴 30분 로그아웃 | 충족 | `core/guard.py:36-41`, `core/auth.py:181-188` | 기본값 30분, 설정 가능 |
| F-09-14 | 공유 링크 토큰(POOL+만료+이메일 바인딩), 로그인 필수 | 충족 | `core/sharing.py`, `app.py:127-148`(토큰 보관만 하고 검증은 로그인 후) | |
| F-09-15 | 발급 시 수신자/목적/범위/만료일 필수 + 로그 | 충족 | `core/sharing.py:80-104`, `pages/8_공유_관리.py:41-59` | |
| F-09-16 | 즉시 회수 | 충족 | `core/sharing.py`(revoke), `pages/8_공유_관리.py:104-115` | 회수 후 즉시 차단은 Part 2 #12 에서 별도 검증 |
| F-09-17 | 워터마크 + 대외비 고지 상시 | 충족 | `core/guard.py:70-76`(confidential_notice→confidential_banner), `reports/pdf.py:227-249`(모든 페이지 워터마크), `reports/xlsx.py` | |
| F-09-18 | 우클릭 제한 등 시도하지 않음 | 충족(부작위로 충족) | 코드 전체에 그런 시도 없음 | |
| F-09-19 | HTTPS 강제 | **미구현** | — | `.streamlit/config.toml`에 TLS 관련 설정 없음, 리버스 프록시·Nginx 설정 파일이 저장소에 없음. 배포 인프라 단계 미착수 |
| F-09-20 | secrets 미커밋, 환경변수 주입 | 충족 | `.gitignore:2-3`(secrets.toml, .env), `.env.example`/`secrets.toml.example`만 추적됨(Part 3에서 재확인) | |
| F-09-21 | Docker 패키징 + 3환경 분리 | **미구현** | — | Dockerfile·docker-compose 등 저장소에 없음(확인: glob 결과 없음) |
| F-09-22 | 접근 로그 애플리케이션 적재 | 충족 | `core/audit.py`, `data/models.py:397-413`(AccessLog), `pages/7_관리자.py`(접근로그 탭) | |
| F-09-23 | 배포 시 공지 배너 | **미구현** | — | 그런 배너 컴포넌트·문구 없음 |

### R-01~R-08 (§5.1 스크리닝 룰)

| 룰 | 내용 | 상태 | 근거 |
|---|---|---|---|
| R-01 | 자사·계열사 상근/냉각기간 재직 | 충족 | `core/screening.py:185-206`(rule_r01), 냉각기간 `SET_COOLING_OFF_YEARS` 기본 2년(PRD "최근 2년"과 일치) |
| R-02 | 최대주주 특수관계 | 충족 | `core/screening.py:208-222` |
| R-03 | 이해상충 기관 | 충족 | `core/screening.py:225-237` |
| R-04 | 겸직 한도 초과 | 충족 | `core/screening.py:240-254` |
| R-05 | 재직연수 상한(연속/계열합산) | 충족 | `core/screening.py:257-285` |
| R-06 | 형사/제재/부정거래 | 충족 | `core/screening.py:288-314`, 미확인 건은 판정 미반영(PRD F-03(5) 원칙과 일치) |
| R-07 | 감사위원 요건 | 충족 | `core/screening.py:317-337`(정보성 ℹ️) |
| R-08 | 성별 단독구성 금지 대상 | 충족 | `core/screening.py:340-352`(정보성 ℹ️) |

### §5.2 개인정보·명예 요건

| 항목 | 상태 | 근거 | 비고 |
|---|---|---|---|
| 민감정보·고유식별정보 수집 금지 | 충족(스키마상) | `data/models.py` Person 모델에 건강·정치성향·주민번호 등 필드 자체가 없음 | 구조적으로 저장 불가 |
| 최소 수집 | 충족 | 연락처·주소 필드 없음(Person 모델 확인) | |
| 보관 3년 + 자동 파기 | 충족 | `core/ingest.py:296-315`(purge_expired), `batch/run.py purge`, `core/settings.py`(SET_RETENTION_YEARS=3) | `tests/test_ingest.py`로 검증됨 |
| 삭제요청 즉시 파기+재수집 차단 | 충족 | `core/ingest.py:318-331`(delete_person_request, PersonBlocklist) | |
| 명예훼손 리스크(확인된 사실만) | 충족 | `core/reputation.py`, `pages/2_후보_상세.py:322-351`(미확인 구분 표기, 점수 미반영) | |
| 접근통제 + 조회출력 로그 | 충족 | `core/guard.py`, `core/audit.py` | |
| robots.txt 준수 | 충족(인터페이스) | `collectors/web.py:22-33`(can_fetch) | 실제 라이브 크롤링 미구현이라 실전 검증은 못함 |

### §10 비기능 요구사항

| 항목 | 상태 | 근거/비고 |
|---|---|---|
| 성능(검색 3초, 100명) | 충족(개발 규모 기준) | 2-14에서 실측 0.016~0.065초(SQLite, 200명). **"10만 인물 기준"은 검증 불가** — 현재 규모로는 테스트 불가능하고 PostgreSQL 전환·인덱싱 전략도 미검증 |
| 확장성(50만명/500만건) | 확인 불가 | 스키마상 특별한 제약은 없으나 실측 불가 |
| 가용성 99.5% | 확인 불가 | 배포 인프라 미구축(F-09-21 참고) |
| 보안 | 부분충족 | HTTPS(F-09-19)·SSO(F-09-10 일부)·Docker(F-09-21) 미구현. 나머지(RBAC 재검증·워터마크·공유만료)는 충족 |
| 감사성(3년 보관) | 부분충족 | AccessLog 적재는 충족. **AccessLog 자체의 3년 보관·파기 정책은 구현 안 됨**(Person 보관기간만 파기 대상, AccessLog/AuditLog는 무기한 누적) |
| 정확성(출처 0건) | 충족 | `data/repository.py:190-220`, 전 테스트에서 0건 유지 확인 |
| 접근성(1280px) | 충족 | 3단계에서 Playwright 1280×900 9개 화면 전수 검증 |
| 유지보수성(core 분리, 커버리지 70%↑) | 충족 | 커버리지 93%(2-14 실측), `core/`↔`pages/` 계층 분리 준수 |

---

## Part 2 — 인수 기준(§13) 검증

| # | 기준 | 검증 방법 | 결과 |
|---|---|---|---|
| 1 | 드롭다운만으로 전 필터 검색 | 코드 확인 — `pages/1_후보_검색.py` 전체 위젯이 selectbox/multiselect/radio | **통과** |
| 2 | 목록에 성별·나이·현재직업·겸직수·스크리닝 | `pages/1_후보_검색.py:378-404`(_to_table) | **통과** |
| 3 | 최근10년+임원급, 초과분 자동제외 | `tests/test_career.py`(경계값 포함, 실행 결과 통과) | **통과(자동화됨)** |
| 4 | 잔여임기 O년O개월(월말/윤년/만료/미상) | `tests/test_directorship_term.py`(6개 케이스: None/6개월/5개월/음수/0/윤년) | **통과(자동화됨)** |
| 5 | 출처 URL 누락 0건(전수) | `data/repository.source_integrity_report()` + `tests/test_invariants.py` | **통과 — PRD의 "20인 표본"보다 강한 전수 검증**(스키마 NOT NULL 제약이 애초에 위반을 불가능하게 함) |
| 6 | 결격사유 상단 미노출 | `core/search.py:266-283`(fail_rank 최상위 정렬키), `pages/1_후보_검색.py:410-437`(정상/결격 테이블 분리) | **통과** |
| 7 | 결격 🔴 구분 표시 | `core/constants.py:37-42`(SCREEN_BADGE) | **통과** |
| 8 | 미검수 PDF 차단 | `tests/test_report_gate.py`, `tests/test_pages_render.py::test_report_page_blocks_unreviewed_*`(버튼 disabled 확인) | **통과(자동화됨)** |
| 9 | 표본 20인 팩트 오류율 3%↓ | — | **검증 불가 — 자동화 대상 아님.** 합성 더미데이터 단계라 "팩트 오류"라는 개념 자체가 성립하지 않는다. 실제 데이터 투입 후 사무국의 인적 검수 프로세스로만 측정 가능 |
| 10 | 비로그인 URL 직접 접근 차단 | `tests/test_pages_guard.py`(9개 페이지 전수 미인증 접근 테스트) | **통과(자동화됨)** |
| 11 | 외부뷰어 권한 우회 시도 | `tests/test_sharing.py`, `tests/test_viewer_pages.py`(세션 role 조작해도 DB 기준으로 판단하는지 검증) | **통과(자동화됨).** 이번 검토에서 추가로 "로그아웃 없이 세션 사용자만 바뀌는" 시나리오를 AppTest로 별도 재현했고, `access.filter_person_options` 재계산 덕에 권한 우회는 발생하지 않음을 확인(§Part 4 참고) |
| 12 | 공유 링크 회수/만료 즉시 반영 | `tests/test_sharing.py`(revoke 후 즉시 verify_token 실패 확인) | **통과(자동화됨)** |
| 13 | AccessLog 전 행위 기록 | `core/audit.py` 호출 지점 grep 확인 — login/view/search/export/share_issue/share_revoke/share_access 전부 존재 | **통과** |
| 14 | 시크릿 평문 저장소 없음 | Part 3에서 재확인(git ls-files, .env.example 내용 확인) | **통과** |
| 15 | "전체 N명 중 상위 M명" 정확 표기(N=M/0건) | `tests/test_search_limit.py`, `core/ui/components.py:117-141`(result_count_banner 3분기 로직) | **통과(자동화됨)** |
| 16 | 전체 선택 시 시스템 상한 | `tests/test_search_limit.py`, `core/search.py`(resolve_limit) | **통과(자동화됨)** |
| 17 | 100명 조회 3초 이내 | 2-14 실측: 0.016~0.065초(3회 평균, SQLite 200명) | **통과 — 단, 개발 규모 기준.** 운영 규모(PostgreSQL, 수천~수십만 명)에서 재측정 필요 |

---

## Part 3 — 보안 점검 (PRD 부록 C, 12개 항목)

| # | 점검 항목 | 통과 기준 | 판정 |
|---|---|---|---|
| 1 | 익명 접근 차단 | 로그아웃 상태 전 페이지 URL 직접 호출 시 미노출 | **통과** — `tests/test_pages_guard.py` |
| 2 | 역할별 권한 | 상위 권한 페이지 URL 직접 호출 차단 | **통과** — 동일 |
| 3 | 외부 뷰어 격리 | 지정 POOL 외 조회 불가, 다운로드 미노출+API 차단 | **통과** — `core/access.py`, `core/auth.can_download`, `tests/test_viewer_pages.py` |
| 4 | 공유 링크 | 만료·회수 즉시 반영, 토큰 단독 불가 | **통과** — `core/sharing.py`, `app.py:135-148`(토큰은 로그인 후에만 검증) |
| 5 | 캐시 | 사용자 종속 데이터가 캐시 키에 사용자ID 포함 또는 미사용 | **통과** — 캐시 사용처가 사실상 1곳(옵션 카운트, 역할 무관 공용 데이터로 근거 명시)뿐이라 위반 소지가 없음. 다만 F-09-2 미구현으로 캐싱 자체가 거의 없다는 점은 성능 관점에서 별도 이슈(Part 1 참고) |
| 6 | 시크릿 | 저장소 미커밋, 스캐너 통과 | **통과** — `git ls-files`로 실제 시크릿 파일 없음 확인(`.example` 템플릿만 추적), `.env.example`은 빈 값 |
| 7 | 전송 구간 HTTPS | 강제·리다이렉트·TLS 유효 | **실패** — F-09-19 미구현. 배포 설정 자체가 저장소에 없음 |
| 8 | 로깅 | 로그인·검색·조회·다운로드·공유 전부 AccessLog | **통과** |
| 9 | 출력물 워터마크 | PDF/XLSX 열람자·일시+대외비 | **통과** — `reports/pdf.py:227-249`, `reports/xlsx.py` |
| 10 | 데이터 범위 | 퍼블릭 환경에 실명 데이터 미배포 | **통과(현재 상태 기준)** — 모든 개발·테스트가 합성 데이터만 사용(`data/seed.py` 주석 명시), 실제 배포가 아직 없어 위반 자체가 발생할 수 없는 상태 |
| 11 | 보관·파기 | retention_until 경과 자동 파기 정상 동작 | **통과** — `core/ingest.py::purge_expired`, `tests/test_ingest.py`로 검증 |
| 12 | 검수 게이트 | 미검수 외부출력 차단 | **통과** — Part 2 #8 참고 |

### 추가 점검 (Part 3 지시사항)

- **SQL 인젝션 가능 지점**: `grep`으로 f-string/format 기반 SQL 조합 패턴을 전수 검색한 결과 **없음**. 모든 쿼리가 SQLAlchemy ORM `select()`/`func`를 통해 구성되며 문자열 결합 방식의 원시 SQL이 전혀 없다.
- **캐시 키에 사용자 컨텍스트 누락**: 위 점검 5 참고. `@st.cache_data`/`@st.cache_resource` 사용처가 전체 코드베이스에 단 2곳뿐이며 둘 다 사용자 종속 데이터가 아니다.
- **세션 상태를 신뢰해 권한을 판단하는 곳**: 없음. `core/guard.py::require()`가 매 요청마다 `core.auth.refresh_user()`로 **DB에서 역할을 다시 읽어** 세션에 저장된 값을 덮어쓴다(`core/guard.py:44-52`). `tests/test_viewer_pages.py`가 "세션 role 을 위조해도 DB 기준으로 판단"함을 명시적으로 검증한다.
- **하드코딩된 비밀정보**: 없음(위 점검 6 참고).
- **에러 메시지·로그의 PII/스택트레이스 노출**: `.streamlit/config.toml`에 `showErrorDetails = false` 설정됨(사용자에게 스택트레이스 비노출). 코드 전체에 `st.exception()` 호출 없음. `core/audit.py`의 로그 적재 실패 시 스택트레이스는 `stderr`로만 나가고(서버 로그, 사용자 비노출) 사용자 화면에는 노출되지 않는다.

---

## Part 4 — 버그 헌팅

실제 코드 실행·재현으로 확인된 항목만 기재한다. 재현하려 했으나 **재현되지 않아 기각한 가설**도 투명성을 위해 별도로 남긴다.

| # | 심각도 | 위치 | 증상 | 재현 경로 | 원인 | 수정 방안 |
|---|---|---|---|---|---|---|
| 1 | Medium | `pages/3_후보_비교.py` (구 코드, 이번 3단계에서 표현만 재구성했고 로직은 그대로 유지) | 비교 화면의 '적합도' 행이 항상 "미산출"만 표시 | 아무 후보 2명 이상을 비교함에 담고 비교 화면 진입 → 적합도 행이 항상 동일 문구 | `scoring.get(person_id)`를 호출하는 상세 화면과 달리, 비교 화면 코드는 `scoring.NOT_IMPLEMENTED_LABEL`을 하드코딩만 하고 실제 점수 조회 로직이 연결돼 있지 않음(`pages/3_후보_비교.py` rows["적합도"] 라인) | `scoring.get(person_id)` 호출해 `scoring.display(...)`로 표시 |
| 2 | Medium | `core/pools.py::update_pool` (90-103행) | POOL 메타데이터(명칭·목적·대상직위·목표인원·기한) 동시 수정 시 나중에 저장한 사람이 조용히 이긴다 | 담당자 A, B가 동시에 같은 POOL 편집 폼을 열고 서로 다른 값을 저장 → 나중 저장이 먼저 저장을 덮어씀, 오류 없음 | `change_state()`는 `expected_state` 파라미터로 낙관적 잠금을 하지만(17-18행 주석에도 명시), `update_pool()`에는 같은 보호가 없음 | `update_pool`에 `expected_updated_at`(또는 버전 컬럼) 파라미터를 추가해 `ConcurrentUpdateError`로 거부 |
| 3 | Medium | F-07 — 동명이인 처리 (Part 1 참고) | `ReviewQueue(QUEUE_IDENTITY)`에 쌓인 항목을 확인·해소하는 화면이 없어 큐가 무한히 쌓임 | `core.ingest.run_dummy_collection()` 실행 → 동명이인 케이스가 큐에 적재됨 → 어떤 화면에서도 조회·해소 불가(코드베이스 전수 grep으로 확인) | 애초에 그 워크플로 단계(§11 "수기 확인 큐로 전송" 이후)가 구현되지 않음 | 관리자 또는 검수 화면에 "동명이인 확인 큐" 탭 추가, 병합/분리 액션 제공 |
| 4 | Low | `core/state.py::clear_user_scoped` (98-121행) | 로그아웃 후 같은 브라우저 세션에서 다른 계정으로 로그인하면, 검색 필터 등 **위젯 바인딩 session_state 키**(`sel_*`, `multi_*`, `w_sort`, `w_limit`, `w_page`, `radio_job_scope` 등)가 지워지지 않아 이전 사용자가 선택했던 값이 새 사용자 화면에 그대로 남는다 | 담당자 A로 로그인 → 검색에서 성별=여성 선택 → 로그아웃 → 담당자 B로 로그인 → 검색 화면 진입 시 성별 필터가 "전체"가 아니라 "여성"으로 미리 선택돼 있음 | `clear_user_scoped()`의 삭제 대상 키 목록에 `core/state.K_*` 상수만 있고, `pages/*.py`에서 `key=` 로 직접 만든 위젯 키들은 빠져 있음(리스트: `pages/1_후보_검색.py`의 `sel_*`/`multi_*`/`radio_job_scope`/`w_sort`/`w_limit`/`w_page`/`preset_*`/`pool_*`, `pages/2_후보_상세.py`의 `detail_person`, `pages/4_POOL_관리.py`의 `pool_select`, `pages/6_리포트.py`의 `report_person`/`report_pool` 등) | 로그아웃 시 `st.session_state.clear()`로 전체 초기화하거나, 위 위젯 키 프리픽스를 일괄 정리하는 헬퍼 추가 |
| 5 | Low | `core/codes.py::load_codes` (F-09-2) | 드롭다운을 열 때마다 DB 쿼리 발생(캐시 없음) | 검색 화면 진입 시 필터마다 `load_codes()` 호출 — 캐시 미적용이라 재실행(rerun)마다 반복 쿼리 | `@st.cache_data(ttl=600)` 데코레이터 누락 | PRD 명시대로 데코레이터 추가(역할 무관 공용 데이터라 캐시 안전) |

### 재현 시도했으나 기각한 가설 (투명성 기재)

- **가설**: "위 버그 #4(위젯 키 잔존)가 권한이 다른 사용자 간(예: 담당자→외부뷰어) 전환 시에는 미노출 데이터를 화면에 그대로 노출시킬 수 있다."
  **재현 시도**: `AppTest`로 담당자가 `detail_person` 위젯 키에 특정 person_id를 선택해 둔 상태를 만든 뒤, 세션의 `K_USER`만 외부뷰어로 바꿔 재실행.
  **결과**: 예외 없이 안전하게 **뷰어의 허용 목록 중 첫 값으로 자동 정정됨**(선택값이 뷰어의 옵션 목록에 없으면 `st.selectbox`가 코드가 계산한 안전한 `index`를 따름). 상세 화면 코드가 `if selected not in name_by_id: selected = options[0][0]`로 이미 방어하고 있고(`pages/2_후보_상세.py:40-42`), 옵션 목록 자체가 매번 `access.filter_person_options(user, ...)`로 새로 계산되기 때문이다.
  **결론**: 버그 #4는 실재하지만 **UX/정확성 문제이지 권한 우회는 아니다.** 모든 페이지가 위젯 값과 무관하게 서버 측에서 "현재 로그인한 사용자가 이 대상을 볼 수 있는가"를 다시 확인하는 패턴(`access.can_view_person`, `access.allowed_pool_ids` 등)을 일관되게 쓰고 있어, 세션 오염이 있어도 실제 데이터 노출로 이어지지 않는다. **이 방어 패턴 자체가 이번 검토에서 확인된 이 코드베이스의 강점**이다.

- **가설**: "적합도 가중치 합이 100이 아니므로 §6.6 수치와 어긋난다."
  **확인**: 기본값 40+20+15+15-10 은 PRD §6.6에 적힌 숫자를 그대로 반영한 것이며, PRD도 "100점 만점을 보장"한다고 명시하지 않았다. 버그 아님 — 기각.

---

## Part 5 — 종합 보고

### PRD 충족률

- 개별 요구사항 ID(F-01~F-09 세부 항목 + R-01~R-08) 기준 **약 84 / 91 충족(약 92%)**.
  - 미구현 6건: F-05-5(재수집·아카이브 자동화 일부), F-07(동명이인 병합/분리 UI), F-09-2(캐싱), F-09-19(HTTPS), F-09-21(Docker), F-09-23(공지배너)
  - 부분충족 3건: F-03(5) 거버넌스 이력, F-05-5, F-05-6
  - 요구사항과 다르게 구현 1건: F-09-6(expander→popover, PRD 자체 모순에 기인)
- §10 비기능 중 성능·정확성·접근성·유지보수성은 충족, 확장성·가용성은 미배포로 확인 불가, 보안은 부분충족(HTTPS·Docker 누락).

### 운영 배포 전 반드시 고쳐야 할 항목 (Critical + 보안 부록C 실패)

이번 검토에서 **Critical 등급 버그는 발견되지 않았다.** 다만 배포 전 필수 항목은:

1. **부록 C #7 HTTPS 강제** — 현재 미구현. 리버스 프록시(Nginx)·TLS 설정 또는 배포 플랫폼의 HTTPS 종단 처리가 필요.
2. **F-09-21 Docker 패키징** — PRD가 "Docker 컨테이너 1식 + 배치 컨테이너"를 배포 형태로 못박고 있음(§8). 현재 전무.
3. **F-09-10 SSO/OIDC 실연동** — 현재 mock 인증만 존재. `OIDCAuthProvider`는 인터페이스만 있고 `NotImplementedError`.
4. **실제 수집기(DART·뉴스·홈페이지) 구현 + API 키/계약** — 이게 없으면 애초에 실제 후보자 데이터가 시스템에 들어올 방법이 없다(PRD §14 미결 #1·#2와 직결).
5. **F-07 동명이인 병합/분리 화면** — 실제 데이터 투입 시 동명이인 오식별은 PRD §11에서 "치명적" 리스크로 명시한 항목인데, 그 대응의 마지막 단계(사람이 확정)가 비어 있다.

### 고치면 좋은 항목 (Medium/Low, Critical 아님)

- `core/pools.py::update_pool` 동시성 보호 추가 (버그 #2)
- 로그아웃 시 위젯 session_state 전체 정리 (버그 #4) — 보안 문제는 아니지만 매 세션마다 혼란을 유발
- `core/codes.py::load_codes` 캐싱 적용 (버그 #5, F-09-2)
- `pages/3_후보_비교.py` 적합도 실제 점수 연결 (버그 #1)
- F-05-5 URL 실효성 상실 시 재수집/아카이브 자동화
- F-09-23 배포 공지 배너
- AccessLog/AuditLog 자체의 보관기간 정책(§10 감사성이 "3년 보관"을 요구하는데 파기 로직은 Person 데이터에만 있음)

### PRD 자체를 수정해야 할 항목

- **F-05-2 vs F-09-6 모순**: F-05-2는 "팝오버로 표시", F-09-6 구현 세부사항은 "`st.expander(\"출처 보기\")` 안에 표시"라고 서로 다른 컴포넌트를 지정한다. 현재 구현은 F-05-2(팝오버)를 따랐다. **PRD에서 F-09-6을 "팝오버(`st.popover`)로 표시"로 정정하는 것을 제안**하며, 이 판단에 대해 사용자 확인을 요청한다 — 혹시 expander 방식을 의도적으로 원했다면 되돌릴 수 있다.
- **§10 성능 요구사항("10만 인물 기준")**: 현재 개발 단계에서 실측이 원천적으로 불가능한 규모다. PRD에 "MVP/개발 단계에서는 축소 규모로 검증하고, 운영 전환 시 재측정"이라는 단서를 추가하는 것을 제안한다(이미 PROGRESS.md에는 비공식으로 기록돼 있으나 PRD 자체엔 없음).
- **F-07 "병합/분리 기능"의 구체적 범위**가 PRD에 UI 요구사항으로 명시돼 있지 않다(그냥 "기능"이라고만 되어 있음). 어떤 화면(관리자/검수)에 둘지, 병합 시 기존 사실 데이터를 어떻게 재배정할지 설계 방향이 필요하므로 **§14 미결 사항에 새 항목으로 추가**하는 것을 제안한다.

---

## 진행 방식 안내

이 보고서는 Part 1~5 전수 검토 결과이며 **코드는 수정하지 않았다.** 다음 중 어디까지 수정 범위로 지정할지 알려주면 그 범위만 수정하고, 수정 항목별로 재검증 결과를 다시 보고하겠다.

- (A) Critical/배포 전 필수 항목만
- (B) 위 "고치면 좋은 항목"까지 포함
- (C) 특정 항목만 선택(번호로 지정)
- (D) PRD 문서 수정(모순 정정, §14 항목 추가)부터 먼저
