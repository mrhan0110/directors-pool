# 독립이사 후보자 POOL — Streamlit 앱 + 배치 공용 이미지 (PRD §8, F-09-21)
#
# 같은 이미지를 두 가지 방식으로 쓴다:
#   - 웹 서비스: 기본 CMD(streamlit run app.py)
#   - 배치(수집·분석): docker compose run --rm batch python -m batch.run analyze
#
# 개발/스테이징/운영 구분은 이미지가 아니라 환경변수(.env)로 한다(F-09-21) — 이미지는 하나다.

FROM python:3.11-slim AS base

# 한글 폰트(사추위 보고용 PDF, reports/pdf.py) — 시스템 폰트가 없으면 내장 CID 폰트로
# 자동 폴백하지만(font_name()), 실제 배포에서는 나눔고딕을 넣어 품질을 높인다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

# 컨테이너 안에서는 비루트 사용자로 실행한다.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/storage /app/storage/snapshots \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDF_FONT_PATH=/usr/share/fonts/truetype/nanum/NanumGothic.ttf \
    DATA_MODE=dummy \
    AUTH_PROVIDER=mock

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)" || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
