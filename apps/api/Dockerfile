FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.lock
COPY . .
RUN pip install --no-deps . && useradd --create-home --uid 10001 nexora && mkdir -p /data/uploads && chown nexora /data/uploads
ENV RUFF_CACHE_DIR=/tmp/nexora-ruff MYPY_CACHE_DIR=/tmp/nexora-mypy
USER nexora
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
