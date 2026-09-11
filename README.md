# 독립이사 후보자 POOL

상장회사 이사회 사무국이 독립이사(사외이사) 후보자 POOL을 구축·관리하는 사내 Streamlit 앱.
요구사항 원천은 `PRD_독립이사_후보자_POOL.md`, 구현 순서는 `PROMPTS_단계별_개발.md`를 따른다.

> **현재 단계: 1단계(기본 뼈대) 완료.** 화면 이동·권한 가드·드롭다운 검색·더미데이터까지 동작한다.
> 수집·분류·점수·PDF 등 실제 기능은 2단계에서 구현한다.

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
| `DART_API_KEY`, `NEWS_API_KEY` | 비움 | 2단계 수집기용. 코드에 하드코딩 금지 |
| `SEED_PERSON_COUNT` | `200` | 시드 후보자 수 (테스트는 25) |

## 시드 데이터 생성

```powershell
python -m data.seed            # 없는 것만 추가 (CodeMaster, 설정값, 계정, 후보 200명, POOL 2개)
python -m data.seed --reset    # 전체 삭제 후 재생성 (확인 프롬프트 있음)
```

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

> 전역 Python에 `langsmith`가 설치돼 있으면 그 pytest 플러그인이 `requests_toolbelt` 누락으로 pytest 기동을 막을 수 있다.
> `.venv`에서 실행하거나, `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'`을 설정한 뒤 실행한다.

## 구조

```
app.py            진입점 · 모의 로그인
pages/            Streamlit 화면 (0 대시보드 ~ 8 공유 관리). 모든 페이지 최상단에서 권한 재검증
core/             도메인 로직 (search, scoring, screening, expertise, career, auth, audit, state, settings, codes, guard)
data/             SQLAlchemy 모델 · repository · 세션 · 시드
collectors/       DART · 뉴스 · 웹 수집기 (1단계는 인터페이스만, Streamlit 밖 배치로 실행)
reports/          PDF/XLSX 출력 (1단계는 출력 게이트만)
tests/            pytest
```

`pages/`에는 SQL·비즈니스 로직을 두지 않는다. 전부 `core/`와 `data/repository`를 거친다.
