# The analysis worker on the GPU. The cu128 torch wheels carry their own CUDA libraries, so a slim
# base is enough; the NVIDIA runtime gives the container the driver. The models are never baked
# in here: the host's Hugging Face cache is mounted read-only at /hf (HF_HUB_OFFLINE=1).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HF_HOME=/hf HF_HUB_OFFLINE=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

WORKDIR /srv
COPY pyproject.toml uv.lock ./
COPY vendor ./vendor
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra worker
COPY app ./app

# uid 1000: the owner of the host model cache mounted at /hf (compose runs it as that user)
RUN useradd --uid 1000 --create-home mojawid
USER mojawid
EXPOSE 8200
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s \
  CMD python -c "import json, urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8200/healthz'))['ready']"
CMD ["uvicorn", "app.worker.main:app", "--host", "0.0.0.0", "--port", "8200"]
