# Cognifin (FinSight AI)

RAG-based question answering over Indian financial documents (NIFTY 100 annual reports and quarterly results, SEBI DRHP/RHP). Ask a natural-language question, get an LLM answer grounded in cited evidence from the source PDFs.

## Stack

- **Backend:** FastAPI, PyMuPDF, sentence-transformers, FAISS, OpenAI
- **Frontend:** React + Vite

## Structure

```
backend/   FastAPI API, ingestion, retrieval pipeline, query understanding
frontend/  React UI (question box, answer, evidence list)
```

## Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # then set JWT_SECRET, OPENAI_API_KEY, MONGO_URI
uvicorn main:app --reload      # http://localhost:8000/docs
```

### Ingest documents

PDFs are not committed. Place them at `backend/data/<SYMBOL>/<YEAR>.pdf`, then:

```bash
python ingestion/batch_ingest_annual_reports.py
```

The FAISS index is cached in `backend/index_cache/` (git-ignored). You can also upload a PDF at runtime via `POST /upload`.

**Re-indexing on a local GPU.** Embedding the full corpus with `bge-base-en-v1.5` is hours on CPU and minutes on an NVIDIA GPU. `requirements.txt` stays CPU-only (the server has no GPU), so install the CUDA build of PyTorch into your local venv only:

```bash
pip install --force-reinstall --no-deps torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.cuda.is_available())"   # True
```

The batch script then embeds in fp16 on the GPU automatically. Start from an empty `backend/index_cache/`; changing the chunker, `EMBEDDING_MODEL` or `QUERY_INSTRUCTION` always needs a full re-index.

### Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

The frontend calls the API at `http://localhost:8000` (see `frontend/src/api.js`).

## API

| Method | Path        | Purpose                        |
|--------|-------------|--------------------------------|
| GET    | `/health`   | Health check                   |
| POST   | `/upload`   | Ingest an uploaded PDF         |
| POST   | `/retrieve` | Retrieve evidence only         |
| POST   | `/chat`     | Retrieve + generate answer     |

## Configuration

Every setting is a field in `backend/config.py`, documented in `backend/.env.example`. The API refuses to start without a real `JWT_SECRET`, and rejects `.env` keys it doesn't know. Never commit `.env`.

## Tests

```bash
cd backend
python -m pytest
```

## Deploy

Frontend on Vercel; API on one small Linux VM (Azure for Students: `Standard_B2ats_v2`, 2 vCPU / 1 GiB) behind Caddy, which handles HTTPS. MongoDB Atlas M0 for users and chats, Hugging Face datasets for the index and the PDFs.

**1. Publish the index (private dataset).** From a machine that has `backend/index_cache/`:

```bash
cd backend/index_cache && tar czf ../index_cache.tar.gz lancedb document_registry.json financials.duckdb
hf repo create <user>/cognifin-index --repo-type dataset --private
hf upload <user>/cognifin-index ../index_cache.tar.gz index_cache.tar.gz --repo-type dataset
```

`HF_CACHE_URL` is `https://huggingface.co/datasets/<user>/cognifin-index/resolve/main/index_cache.tar.gz`, and `HF_TOKEN` a fine-grained token with read access to that one dataset. The API downloads it into a Docker volume on first boot (~3 GB, a few minutes).

**2. PDFs (public dataset).** Answers link to the PDFs from the browser, which cannot send a token, so this dataset is public (they are published annual reports anyway). Keep the `SYMBOL/YEAR.pdf` layout:

```bash
hf repo create <user>/cognifin-pdfs --repo-type dataset
hf upload-large-folder <user>/cognifin-pdfs backend/data --repo-type dataset --include "*/*.pdf"
```

`HF_PDF_BASE_URL` is `https://huggingface.co/datasets/<user>/cognifin-pdfs/resolve/main`. Hugging Face already serves byte ranges with CORS, so the PDF viewer needs no bucket policy.

**3. MongoDB Atlas.** Create an M0 cluster and allow the server's IP under Network Access, then **delete the `0.0.0.0/0` (allow from anywhere) entry** used during development, so only the server can connect. The connection string is `MONGO_URI`.

**4. The API box.** Open ports 80 and 443 and give the VM a hostname: your own DNS A record, or Azure's free label (`az network public-ip update -g <rg> -n <vm>PublicIP --dns-name <label>` gives `<label>.<region>.cloudapp.azure.com`). Azure for Students only allows a few regions (`az policy assignment list` shows them). On the VM, add a 2 GB swap file and install `docker.io docker-compose-v2 docker-buildx`. Two Azure gotchas:

- Containers can't finish TLS handshakes at MTU 1500 there (pip and downloads hang). Set `{"mtu": 1400, "default-network-opts": {"bridge": {"com.docker.network.driver.mtu": "1400"}}}` in `/etc/docker/daemon.json` and restart Docker.
- The image's first stage exports the models to ONNX with PyTorch, which needs ~2 GB RAM and thrashes a 1 GiB VM. Export on any bigger machine (`python -m ingestion.export_onnx --out models_onnx`), copy `models_onnx/*/{model_int8.onnx,tokenizer.json}` to the VM under `~/onnx_ctx/models_onnx/`, and build only the runtime with that folder standing in for the stage: `docker buildx build --load --build-context export=$HOME/onnx_ctx -t cognifin-api ./backend`, then `docker compose up -d --no-build`.

Otherwise:

```bash
git clone <this repo> && cd Cognifin
cp backend/.env.example backend/.env   # fill in the values below
echo "API_DOMAIN=api.example.com" > .env
docker compose up -d --build
docker compose logs -f api             # first boot downloads + loads the index
```

Production values in `backend/.env` (compose sets `ASSET_MODE` and `INDEX_CACHE_DIR` itself):

| Key | Value |
|---|---|
| `JWT_SECRET` | a fresh `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OPENAI_API_KEY`, `MONGO_URI` | from steps 3 and your provider |
| `HF_CACHE_URL`, `HF_TOKEN`, `HF_PDF_BASE_URL` | from steps 1 and 2 |
| `ALLOWED_ORIGINS`, `FRONTEND_URL` | `https://YOUR-APP.vercel.app` |
| `GOOGLE_REDIRECT_URI` | `https://api.example.com/auth/callback` (also add it in Google Cloud Console) |

**5. Vercel.** Import the repo with root directory `frontend` and set `VITE_API_BASE=https://api.example.com` and `VITE_SITE_URL=https://YOUR-APP.vercel.app`. The build fails on purpose if `VITE_API_BASE` isn't an https URL.

**6. Check it.** `curl https://api.example.com/health` should report `"indexed": true`. On the site, a suggested question answers instantly (pre-warmed at boot). Logged out, the 6th question returns the sign-in prompt. A citation's PDF opens from the Hugging Face dataset.
