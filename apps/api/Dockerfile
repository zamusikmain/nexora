FROM python:3.13-slim AS runtime
WORKDIR /app
COPY pyproject.toml requirements.runtime.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.runtime.lock
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-deps . && useradd --create-home --uid 10001 nexora && mkdir -p /data/uploads && chown nexora /data/uploads
USER nexora
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

FROM runtime AS development
USER root
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.lock
COPY tests ./tests
ENV RUFF_CACHE_DIR=/tmp/nexora-ruff MYPY_CACHE_DIR=/tmp/nexora-mypy
USER nexora

FROM runtime AS production
