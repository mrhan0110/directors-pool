# 독립이사 후보자 POOL

상장회사 이사회 사무국이 독립이사(사외이사) 후보자 POOL을 구축·관리하는 사내 Streamlit 앱.
요구사항 원천은 `PRD_독립이사_후보자_POOL.md`, 구현 순서는 `PROMPTS_단계별_개발.md`를 따른다.

> **현재 단계: 3단계(UI 디자인) 완료 + 4단계 검토 보고서 작성 완료(`REVIEW_보고서.md`).** 검색·상세·비교·
> POOL 관리·검수·리포트(PDF/XLSX)·공유·관리자 화면과 스크리닝·전문분야 분류·적합도 점수·수집 적재
> 파이프라인이 실제 로직으로 동작하며, 전 화면이 `core/ui/`(테마·재사용 컴포넌트·차트) 한 곳의 통일된
> 스타일을 공유한다. 4단계 검토에서 발견한 버그·PRD 미충족 항목은 `REVIEW_보고서.md`에 정리했고,
> 사용자 승인 대기 중이다.
>
> **실사용 전환 트랙(4단계 승인과 별도로 진행 중)**: DART 실제 수집기(`collectors/dart.py`)를 DART
> 개발가이드 공식 명세로, 뉴스 수집기(`collectors/news.py`)를 네이버 뉴스검색 오픈API(무료, PRD
> §14-2 계약 확정 전 임시 대안)로 구현했다 — 단, **API 키가 없어 둘 다 실제 응답으로 검증하지
> 못했다**(공식 문서 스펙 + 방어적 파싱만으로 작성). 기업 홈페이지 수집(`collectors/web.py`)은 범용
> 베이스워크(robots.txt 확인 + 제목·메타설명·본문 일반 추출)만 있다 — 사이트마다 구조가 달라 특정
> 회사를 정확히 뽑아내려면 회사별 파서가 추가로 필요하다. Docker 패키징(`Dockerfile`,
> `docker-compose.yml`)도 준비했지만 **이 환경에 Docker 가 없어 실제 빌드는 못 해봤다**.

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
| `DART_API_KEY` | 비움 | DART 실제 수집기용. 코드에 하드코딩 금지. [opendart.fss.or.kr](https://opendart.fss.or.kr)에서 무료·즉시 발급 |
| `DART_BSNS_YEAR` | 작년 | DART 임원현황 조회 사업연도(4자리). 정기보고서는 익년에 공시되므로 기본은 작년 |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 비움 | 뉴스 수집기(네이버 뉴스검색 오픈API)용. [developers.naver.com](https://developers.naver.com)에서 무료·즉시 발급 |
| `SEED_PERSON_COUNT` | `200` | 시드 후보자 수 (테스트는 25) |

`DATA_MODE=live`로 실제 DART 수집을 돌리려면 위 `DART_API_KEY`에 더해, 관리자 화면(또는
`AppSetting` 테이블)의 `collect.dart_target_companies` 값을 `고유번호:회사명` 쌍(콤마로 여러 개)으로
채워야 한다 — 초기 수집 대상 회사 범위는 PRD §14-1 결정 대기 사항이라 코드에 기본값을 넣지 않았다.
뉴스 수집(`collectors/pipeline.ingest_news_for_person`)은 아직 배치 CLI에 연결하지 않았다 — 후보
1인 단위로 호출하는 라이브러리 함수로만 존재한다(동명이인 위험이 있어 전량 자동화보다 선별 호출이
안전하다고 판단했다).

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
전체 테스트 370여 건이 통과하며, `core`·`data`·`batch`·`collectors` 코드 커버리지는 94%다
(`collectors/*.py`도 `requests.get`을 monkeypatch 로 흉내 낸 응답으로 파싱·적재 로직은 검증했지만,
실제 네트워크 호출 자체는 API 키가 없어 검증하지 못했다).

```powershell
# 커버리지 리포트 (PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 이 pytest-cov 자동 등록도 막으므로 -p 로 명시한다)
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
pytest -p pytest_cov.plugin -p no:logging --cov=core --cov=data --cov=batch --cov=collectors --cov-report=term-missing
```

> 전역 Python에 `langsmith`가 설치돼 있으면 그 pytest 플러그인이 `requests_toolbelt` 누락으로 pytest 기동을 막을 수 있다.
> `.venv`에서 실행하거나, `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'`을 설정한 뒤 실행한다.

## Docker (PRD §8, F-09-21 — 코드만 준비된 상태, 아래 "알려진 제약" 참고)

```powershell
cp .env.example .env    # POSTGRES_PASSWORD 등 값 채우기
docker compose up -d --build                                   # 웹 앱 (localhost:8501)
docker compose run --rm batch python -m data.seed               # 더미데이터 시드
docker compose run --rm batch python -m batch.run analyze       # 배치 1회 실행
```

같은 이미지를 웹(`app`)과 배치(`batch`, `profiles: ["batch"]`라 `up`으로는 안 뜨고 `run`으로만 실행)에
공용으로 쓴다. `db`(PostgreSQL)까지 3개 서비스 구성이며, 정기 배치 실행(F-05 (3) 갱신 주기)은 이 파일만으론
스케줄링되지 않으므로 운영에서는 호스트 cron 등이 `docker compose run batch ...`를 주기적으로 호출해야 한다.
HTTPS 종단은 `deploy/nginx.conf.example`을 실제 도메인·인증서로 채워 앞단에 둔다.

## 구조

```
app.py            진입점 · 모의 로그인
pages/            Streamlit 화면 (0 대시보드 ~ 8 공유 관리). 모든 페이지 최상단에서 권한 재검증
core/             도메인 로직 (search, scoring, screening, expertise, career, ingest, auth, audit, state, settings, codes, guard, sharing, access, pools, review …)
core/ui/          화면 표현 계층 — style.py(전역 CSS 1곳) · components.py(배지·팝오버·게이지·배너 등) · charts.py(Altair)
data/             SQLAlchemy 모델 · repository · 세션 · 시드
collectors/       DART(실제 API 연동, 키 없어 미검증) · 뉴스(네이버 뉴스검색, 키 없어 미검증) ·
                  웹(범용 베이스워크만, 회사별 정밀 추출 없음) 수집기 + pipeline.py(core.ingest 연결)
reports/          PDF/XLSX 출력 (개인 프로파일·POOL 요약, 워터마크·검수완료 게이트 적용)
batch/            Streamlit 밖 배치 실행기(analyze/classify/screen/score/collect/url-check/purge)
tests/            pytest (약 350건)
deploy/           배포 템플릿(nginx.conf.example — 실제 도메인·인증서로 채워야 함)
Dockerfile, docker-compose.yml, requirements-docker.txt   Docker 패키징(§8, F-09-21)
```

`pages/`에는 SQL·비즈니스 로직을 두지 않는다. 전부 `core/`와 `data/repository`를 거친다.

## 알려진 제약

- **DART·뉴스 수집기는 API 키로 검증되지 않았다**: `collectors/dart.py`(DART 개발가이드)와
  `collectors/news.py`(네이버 뉴스검색 오픈API 공식 swagger 명세)를 각각 실제 API 문서를 확인해
  작성했고 단위테스트도 있지만, 개발 세션에 키가 없어 **실제 응답으로는 한 번도 호출해보지 못했다.**
  날짜·필드 형식이 문서와 다르면 방어적으로 `None`을 반환하도록 만들어뒀지만, 키를 발급받으면
  1건이라도 실제로 돌려서 결과를 눈으로 확인하는 것을 권장한다.
- **뉴스 수집은 임시 대안이다**: PRD §14-2(뉴스 소스 계약: 빅카인즈/상용 API/언론사 제휴)가 아직
  정해지지 않아, 무료·즉시 발급 가능한 네이버 뉴스검색으로 우선 연동했다. 계약이 정해지면 교체해야
  한다. 또한 뉴스 검색은 이름 문자열만으로 걸러지므로 흔한 이름이면 동명이인 기사가 섞여 들어올 수
  있다 — 전부 `verified_yn=False`로 적재되고 검수(F-08)에서 사람이 걸러내야 한다.
- **기업 홈페이지 수집은 범용 베이스워크뿐이다**: `collectors/web.py`는 robots.txt 확인 후 제목·
  메타설명·본문 문단을 일반적인 방식으로 뽑기만 한다. 회사마다 페이지 구조가 달라 "경영진 소개"
  같은 특정 항목을 정확히 분리해내지 못하므로, 이 출력을 그대로 신뢰해 저장하면 안 되고 검수에서
  반드시 사람이 확인해야 한다.
- **Docker 이미지를 실제로 빌드해보지 못했다**: `Dockerfile`·`docker-compose.yml`을 준비했지만
  이 개발 환경에 Docker 가 설치돼 있지 않아 `docker build`/`docker compose up`을 실행해 검증하지
  못했다(YAML 문법만 확인). 처음 빌드할 때 결과를 확인해야 한다.
- **SSO(OIDC) 미연동**: `AUTH_PROVIDER=oidc`는 인터페이스만 있고 3.5단계 작업이다. 현재는 `mock`(역할 선택 모의 로그인)만 동작한다.
- **HTTPS 종단 미설정**: `deploy/nginx.conf.example`은 도메인·인증서를 채워야 쓸 수 있는 템플릿이다.
- **PRD §14의 16개 미결 사항**(모집단 범위, 뉴스 API 계약, 법령 임계값 확정치 등)은 여전히 결정 대기이며,
  해당 값은 전부 `AppSetting`(관리자 화면에서 수정 가능)의 보수적 기본값으로 채워져 있다.
- **4단계 검토에서 발견한 버그·PRD 미충족 항목**은 `REVIEW_보고서.md` 참고(Critical 없음, 수정 범위는
  사용자 승인 대기).
