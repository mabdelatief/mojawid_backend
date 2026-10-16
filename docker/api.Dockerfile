# The public API: no torch, no ffmpeg (it never decodes audio; the worker does).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1

WORKDIR /srv
COPY pyproject.toml uv.lock ./
COPY vendor ./vendor
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra api
COPY alembic.ini ./
COPY app ./app

RUN useradd --system --uid 10001 mojawid
USER mojawid
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz')"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8100"]
