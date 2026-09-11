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
- 2단계: 🔄 진행 중

## ▶ 다음 작업

**2-2. E 스크리닝 룰엔진** (§E). `core/screening.py`의 `evaluate()`를 룰별 함수로 구현, `evaluate_and_store(person_id)`로 저장(override 보존), `tests/test_screening.py` 작성.
- 참고: 2-1에서 settings에 `get_str/get_float/get_list/validate` 추가됨. 자사 판정은 `org_name`이 자사명/계열사명과 **일치 또는 포함**으로 비교.

## 2단계 작업 단위 체크리스트

각 단위 = 구현 + 테스트 + 커밋. 순서대로 진행.

- [x] 2-1 모델·설정 확장 (신규 테이블/컬럼, AppSetting 키, SCREEN_INFO) — §M
- [ ] 2-2 E 스크리닝 룰엔진 R-01~R-08 (`core/screening.py`) — §E
- [ ] 2-3 D 전문분야 자동 분류 (`core/expertise_rules.py`, `core/expertise.py`) — §D
- [ ] 2-4 F 적합도 점수 (`core/scoring.py`, PersonScore) — §F
- [ ] 2-5 시드 재작성: 엔진으로 스크리닝·분류·점수 산출, 자사/충돌/수동검수 케이스 포함 + `batch/run.py`
- [ ] 2-6 A 검색 core+화면: 건수 배지, 칩 해제, 프리셋, 최근 인원수 사용자별 저장, 페이지네이션 — §A
- [ ] 2-7 B 결과 목록: 전체 컬럼, 행 선택→상세/POOL 추가/비교, XLSX 내보내기 — §B
- [ ] 2-8 C 상세: 전 섹션, 출처 충돌(대체 정보), 구 정보 배지, 평판 정량, 18개 고려사항 체크리스트 — §C
- [ ] 2-9 H POOL 관리(CRUD·상태 전이·사유·타임라인) + 검수(3분할·승인/수정/삭제·ReviewLog·충돌 알림) — §H
- [ ] 2-10 I 리포트: 사추위 2페이지 PDF(부록 A·B, 워터마크) + POOL PDF/XLSX — §I
- [ ] 2-11 J 인증·공유: OIDC 인터페이스, 외부뷰어 POOL 범위 제한, 공유 링크 발급/회수/검증, 로그 — §J
- [ ] 2-12 G 수집: 더미/실제 모드, DART 클라이언트, 뉴스·웹, 인물 식별(동명이인 큐), 스냅샷, URL 점검, 보관기간 파기 — §G
- [ ] 2-13 관리자: 코드 추가·수정·이력, 설정값 수정·이력 (F-01-7)
- [ ] 2-14 DoD 검증: 커버리지 ≥70%, §13 인수기준 1~9·15~17, 100명 조회 3초, README·CLAUDE.md 갱신

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
- 검색 시 SQL로 전문분야 매칭(40) = 가중치 × (선택 전문분야 중 보유 수 / 선택 수). 미선택이면 `org.board_skill_gaps` 기준
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
