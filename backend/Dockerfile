# Cognifin API. Build context: backend/
#   docker compose build            (from the repo root)
# The index is NOT baked in; the container fetches it into /data at first boot
# (ASSET_MODE=remote, HF_CACHE_URL). The models ARE baked in, as ONNX exports, so
# boot never waits on Hugging Face and the runtime image has no PyTorch (1 GB VM).

# --- 1. Export the embedder + reranker to ONNX (needs PyTorch, thrown away after) ---
FROM python:3.12-slim AS export
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# CPU-only torch first: the default wheel drags in ~2 GB of CUDA libraries.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt requirements-runtime.txt ./
RUN pip install -r requirements.txt
# Must match EMBEDDING_MODEL / RERANKER_MODEL at runtime.
ARG EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENV EMBEDDING_MODEL=$EMBEDDING_MODEL RERANKER_MODEL=$RERANKER_MODEL
WORKDIR /src
COPY config.py ./
COPY ingestion/export_onnx.py ingestion/
RUN python -m ingestion.export_onnx --out /models_onnx

# --- 2. Runtime dependencies only ---
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
COPY requirements-runtime.txt .
RUN pip install -r requirements-runtime.txt

# --- 3. Runtime ---
FROM python:3.12-slim
# MALLOC_ARENA_MAX=2: fewer glibc arenas across threads, ~40 MB less memory held after an upload.
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 MALLOC_ARENA_MAX=2 \
    MODEL_BACKEND=onnx ONNX_DIR=/models_onnx ONNX_INT8=true
RUN useradd --create-home app && mkdir /data && chown app /data
COPY --from=build /venv /venv
COPY --from=export /models_onnx /models_onnx
WORKDIR /app
COPY . .
USER app

EXPOSE 8000
# Only Caddy can reach this port (compose publishes nothing else), so trusting
# its X-Forwarded-For is safe — and required, or every visitor shares one
# rate-limit bucket keyed on Caddy's IP.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
