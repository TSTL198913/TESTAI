FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir \
        pytest \
        pytest-asyncio \
        pytest-cov \
        pytest-timeout \
        httpx \
        respx \
        celery \
        redis \
        bandit \
        pip-audit \
        pylint \
        mypy

COPY . .

RUN groupadd -r testai && useradd -r -g testai testai \
    && chown -R testai:testai /app

USER testai

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]