# Deploying Cognifin

Frontend on Vercel; API on one small Linux VM (Azure for Students: `Standard_B2ats_v2`, 2 vCPU / 1 GiB) behind Caddy, which handles HTTPS. MongoDB Atlas M0 for users and chats, Hugging Face datasets for the index and the PDFs. Everything here fits in free tiers or student credit.

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

**Google sign-in.** In Google Cloud Console → Google Auth Platform: fill in **Branding** (app name, support email, home page, privacy policy `https://YOUR-APP.vercel.app/privacy`, both domains under Authorized domains), **Publish app** on the Audience page, then create a **Web application** client with the redirect URI above. The client secret is shown only once. Cognifin asks only for `openid email profile`, so no Google verification is needed. A new client can take a few hours before it stops returning `redirect_uri_mismatch`.

**5. Vercel.** Import the repo (Git-connected, so every merge to `main` deploys) with root directory `frontend` and set `VITE_API_BASE=https://api.example.com` and `VITE_SITE_URL=https://YOUR-APP.vercel.app`. The build fails on purpose if `VITE_API_BASE` isn't an https URL.

**6. Check it.** `curl https://api.example.com/health` should report `"indexed": true`. On the site, a suggested question answers instantly (pre-warmed at boot). Logged out, the 6th question returns the sign-in prompt. A citation's PDF opens from the Hugging Face dataset.
