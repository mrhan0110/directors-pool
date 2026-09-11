# 독립이사 후보자 POOL

상장회사 이사회 사무국이 독립이사(사외이사) 후보자 POOL을 구축·관리하는 사내 Streamlit 앱.
요구사항 원천은 `PRD_독립이사_후보자_POOL.md`, 구현 순서는 `PROMPTS_단계별_개발.md`를 따른다.

> **현재 단계: 2단계(기능 추가) 완료.** 검색·상세·비교·POOL 관리·검수·리포트(PDF/XLSX)·공유·관리자 화면과
> 스크리닝·전문분야 분류·적합도 점수·수집 적재 파이프라인까지 실제 로직으로 동작한다.
> DART·뉴스·기업 홈페이지의 **실제 외부 API 호출**은 API 키가 없어 미구현 상태이며(`collectors/*.py`),
> `DATA_MODE=dummy`(기본값)로는 동일한 적재 파이프라인(`core/ingest.py`)을 가짜 데이터로 통과시켜 검증한다.
> 다음은 3단계(UI 다듬기)·4단계(검토)이며, `PROMPTS_단계별_개발.md`를 따른다.

> ⚠️ **실명 데이터 금지.** 개발·테스트는 `data/seed.py`가 만드는 합성 더미데이터(`가상001 …`, `example.com` URL)만 사용한다.
> Streamlit Community Cloud 등 퍼블릭 환경에 실명 데이터를 배포하지 않는다 (PRD §6.9 (4)).

## 설치

Python 3.11 이상.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                # 필요 시 값 수정. .env 는 커밋 금지
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./storage/pool_dev.db` | 운영은 PostgreSQL 접속 문자열로 교체 |
| `DATA_MODE` | `dummy` | `dummy` \| `live`. 기본은 더미 모드 |
| `AUTH_PROVIDER` | `mock` | `mock`(역할 선택 모의 로그인) \| `oidc`(이후 단계) |
| `SNAPSHOT_DIR` | `./storage/snapshots` | 원문 스냅샷 경로 (F-05-6) |
| `DART_API_KEY`, `NEWS_API_KEY` | 비움 | 실제 수집기용(키 없으면 `collectors/*.py`는 비활성 상태로 동작). 코드에 하드코딩 금지 |
| `SEED_PERSON_COUNT` | `200` | 시드 후보자 수 (테스트는 25) |

## 시드 데이터 생성

```powershell
python -m data.seed            # 없는 것만 추가 (CodeMaster, 설정값, 계정, 후보 200명, POOL 2개)
python -m data.seed --reset    # 전체 삭제 후 재생성 (확인 프롬프트 있음)
```

시드는 마지막에 실제 배치 엔진(`batch.run analyze`)으로 전문분야 분류·스크리닝·적합도 점수를 산출한다.
더미데이터로 검증한 로직이 곧 운영 로직이다.

## 배치 (Streamlit 밖에서 실행 — PRD F-09-8)

```powershell
python -m batch.run analyze     # 분류 → 스크리닝 → 적합도 (순서 고정)
python -m batch.run classify | screen | score   # 개별 실행
python -m batch.run collect     # 수집(§G). DATA_MODE=dummy(기본)면 파이프라인 검증용 가짜 데이터
python -m batch.run url-check   # 출처 URL 유효성 점검, 404 시 url_alive_yn=False (F-05-5)
python -m batch.run purge       # 보관기간(privacy.retention_years, 기본 3년) 경과 후보 자동 파기 (§5.2)
```

모든 배치 작업의 시작·종료·실패는 `AuditLog(entity="batch")`에 기록되어 화면에서 진행 상태를 조회할 수 있다.

## 실행

```powershell
streamlit run app.py
```

모의 로그인 계정 (역할 선택):

| 계정 | 역할 |
|---|---|
| `staff@example.com` | 담당자 |
| `head@example.com` | 사무국장 |
| `legal@example.com` | 법무 |
| `admin@example.com` | 관리자 |
| `viewer@example.com` | 외부뷰어 (30일 만료) |
| `viewer-expired@example.com` | 외부뷰어 (만료됨 — 접근 차단 확인용) |

## 테스트

```powershell
pytest                                                    # 전체
pytest tests/test_pages_guard.py -v                       # 파일 단위
pytest tests/test_career.py::test_lookback_boundary_exactly_ten_years -v   # 단일 테스트
```

테스트는 임시 SQLite에 소량 더미데이터를 만들어 돌리므로 개발 DB를 건드리지 않는다 (`tests/conftest.py`).
전체 테스트 300여 건이 통과하며, `core`·`data`·`batch`·`collectors` 코드 커버리지는 93%다
(`collectors/*.py`의 실제 API 호출부만 0% — API 키가 없어 검증 불가, 의도된 상태).

```powershell
# 커버리지 리포트 (PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 이 pytest-cov 자동 등록도 막으므로 -p 로 명시한다)
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
pytest -p pytest_cov.plugin -p no:logging --cov=core --cov=data --cov=batch --cov=collectors --cov-report=term-missing
```

> 전역 Python에 `langsmith`가 설치돼 있으면 그 pytest 플러그인이 `requests_toolbelt` 누락으로 pytest 기동을 막을 수 있다.
> `.venv`에서 실행하거나, `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'`을 설정한 뒤 실행한다.

## 구조

```
app.py            진입점 · 모의 로그인
pages/            Streamlit 화면 (0 대시보드 ~ 8 공유 관리). 모든 페이지 최상단에서 권한 재검증
core/             도메인 로직 (search, scoring, screening, expertise, career, ingest, auth, audit, state, settings, codes, guard, sharing, access, pools, review …)
data/             SQLAlchemy 모델 · repository · 세션 · 시드
collectors/       DART · 뉴스 · 웹 수집기 (화이트리스트·robots.txt 가드는 동작, 실제 API 호출부는 키 없어 미구현)
reports/          PDF/XLSX 출력 (개인 프로파일·POOL 요약, 워터마크·검수완료 게이트 적용)
batch/            Streamlit 밖 배치 실행기(analyze/classify/screen/score/collect/url-check/purge)
tests/            pytest (약 300건)
```

`pages/`에는 SQL·비즈니스 로직을 두지 않는다. 전부 `core/`와 `data/repository`를 거친다.

## 알려진 제약 (2단계 완료 시점)

- **DART·뉴스·기업 홈페이지 실제 수집**: API 키가 없어 `collectors/dart.py`·`news.py`·`web.py`의 라이브 호출부는
  `NotImplementedError`로 남아 있다. `DATA_MODE=live`로 전환하기 전에 이 부분을 채워야 한다.
  적재 파이프라인(`core/ingest.py`)은 완성되어 있으므로, 파싱 결과를
  `ingest_fact`/`ingest_industry`/`get_or_create_person`에 연결하면 된다.
- **SSO(OIDC) 미연동**: `AUTH_PROVIDER=oidc`는 인터페이스만 있고 3.5단계 작업이다. 현재는 `mock`(역할 선택 모의 로그인)만 동작한다.
- **PRD §14의 16개 미결 사항**(모집단 범위, 뉴스 API 계약, 법령 임계값 확정치 등)은 여전히 결정 대기이며,
  해당 값은 전부 `AppSetting`(관리자 화면에서 수정 가능)의 보수적 기본값으로 채워져 있다.
