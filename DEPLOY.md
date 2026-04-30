# Deploying the OGDCL RAG app (free tier)

Canonical GitHub repo: **[https://github.com/Nabeel5160/Chatbot](https://github.com/Nabeel5160/Chatbot)**  
Clone: `git clone https://github.com/Nabeel5160/Chatbot.git`

This repo cannot be deployed for you from Cursor: **you** create the accounts; your live URLs appear in each provider’s dashboard (for example `https://ogdcl-rag-api.onrender.com` and `https://your-app.vercel.app`).

**Important:** The **Python API (FastAPI + Chroma + OpenAI)** is a long-running web service with a writable disk for the vector DB. **Vercel is for the React frontend only** ([Vercel](https://vercel.com) is ideal for static/Vite apps). Run the API on **Render**, **Railway**, or **Fly.io**, then point the UI at it with `VITE_API_BASE_URL`.

Recommended split: **API on Render (Docker)** · **UI on Vercel** (or Netlify / Cloudflare Pages).

---

## 1) Backend (Render) — required for full chat

1. Use the GitHub repo above (include `ChatbotDocument.txt` in the default branch if you want the corpus baked into the Docker image).
2. Go to [render.com](https://render.com) → **New +** → **Web Service** → connect **`Nabeel5160/Chatbot`**.
3. Choose **Docker** (uses the root `Dockerfile`).
4. Set environment variables (same as local `.env`), at minimum:
   - `OPENAI_API_KEY`
   - Optional: `CORS_ORIGINS` — set to your **frontend** URL(s), comma-separated, e.g. `https://your-app.netlify.app` (safer than `*`).
5. Deploy. Copy the service URL, e.g. `https://ogdcl-rag-api.onrender.com`.

**Free tier notes:** The service **spins down when idle** (first request after sleep can take ~1 minute). `chroma_db` on the default disk is **ephemeral** unless you add a paid disk — re-run **Upload & Index** after cold starts if vectors are lost.

---

## 2) Frontend (Vercel) — recommended with this repo

Repo: **[Nabeel5160/Chatbot on GitHub](https://github.com/Nabeel5160/Chatbot)**

### A) Connect Git (dashboard)

1. Sign in at [vercel.com](https://vercel.com) → **Add New…** → **Project** → **Import** the GitHub repo **`Nabeel5160/Chatbot`**.
2. Under **Root Directory**, click **Edit** and set it to **`frontend`** (this folder contains `package.json` and `vite.config.ts`).
3. **Framework Preset:** Vite (auto-detected).
4. **Build & Output Settings:** leave defaults (`npm run build`, output `dist`).
5. **Environment Variables** (Production — required before the first successful build that talks to your API):

   | Name | Value (example) |
   |------|------------------|
   | `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com` |

   Use your **Render API URL** with **no** trailing slash.

6. Click **Deploy**. Vercel will show a URL like **`https://chatbot-xxx.vercel.app`** — that is your **public frontend**.

### B) CORS on the API

On Render, set `CORS_ORIGINS` to your exact Vercel URL, e.g. `https://chatbot-xxx.vercel.app` (or comma-separate preview + production URLs). Redeploy the API after changing env vars.

### C) Optional: GitHub Actions → Vercel

If you use the workflow **`.github/workflows/deploy-vercel-frontend.yml`**, add these **repository secrets** in GitHub → **Settings** → **Secrets and variables** → **Actions**:

- `VERCEL_TOKEN` — from Vercel → Account → **Tokens**
- `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` — run `npx vercel link` once in `frontend/` locally, or copy from the Vercel project **Settings → General**.

`VITE_API_BASE_URL` must still be set in the **Vercel** project environment for Production builds.

---

## 2b) Frontend on GitHub Pages (free, same repo as code)

Your public URL (after setup) will be:

**[https://nabeel5160.github.io/Chatbot/](https://nabeel5160.github.io/Chatbot/)**

(If GitHub normalises the username to lowercase in the browser, that is expected.)

### Steps

1. **API still on Render** (or another host)—GitHub Pages only serves **static files**, not Python.
2. In the GitHub repo **[Nabeel5160/Chatbot](https://github.com/Nabeel5160/Chatbot)** → **Settings** → **Pages** → **Build and deployment** → **Source:** choose **GitHub Actions** (not “Deploy from a branch”).
3. **Settings** → **Secrets and variables** → **Actions** → tab **Variables** → **New repository variable**:
   - Name: `VITE_API_BASE_URL`
   - Value: your API origin only, e.g. `https://your-service.onrender.com` (no trailing slash).
4. Push to `main` (or open **Actions** → **Deploy Vite app to Pages** → **Run workflow**). The workflow **`.github/workflows/pages.yml`** builds `frontend/` with `VITE_BASE_PATH=/Chatbot/` and publishes `dist` (not the repo README).
5. On Render, set **`CORS_ORIGINS`** to include `https://nabeel5160.github.io` (or the exact Pages URL GitHub shows after deploy). Redeploy the API.

If the Actions **deploy** job fails with a Pages permission error, confirm step 2 (Pages source = GitHub Actions).

### Troubleshooting: `deploy-pages` → **404** / `Failed to create deployment`

That almost always means **GitHub Pages is not enabled** or the source is still **“Deploy from a branch”** instead of **GitHub Actions**.

1. Open **[Pages settings for this repo](https://github.com/Nabeel5160/Chatbot/settings/pages)**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions** (pick it from the dropdown; do not leave “Deploy from a branch” selected).
3. Save if prompted, wait a few seconds, then in **Actions** re-run **Deploy Vite app to Pages** (**Re-run all jobs**).

**Private repository:** Free GitHub Pages from Actions normally expects a **public** repo. If the repo is private and Pages stays disabled or keeps failing, either make the repo **public** or use **Vercel / Netlify** for the frontend instead.

### Common mistake: `VITE_API_BASE_URL` under **Environments**

GitHub **Settings → Environments** lists things like `github-pages` and `Production`. It is **not** where the API URL goes.

- **Wrong:** Creating an environment literally named `VITE_API_BASE_URL` (as in your Environments list).
- **Right:** **Settings → Secrets and variables → Actions** → open the **Variables** tab (not *Environments*) → **New repository variable** → name `VITE_API_BASE_URL`, value `https://your-api.onrender.com`.

You may **delete** the mistaken `VITE_API_BASE_URL` **environment** (trash icon) so it does not confuse future setup.

### `github-pages` environment shows “1 protection rule”

If deployments **wait forever** or fail after build, open **Environments → github-pages** and review **Deployment protection rules**. For a personal demo, remove **required reviewers** so Actions can publish without a manual approval. Then re-run the workflow.

### If `https://nabeel5160.github.io/Chatbot/` shows only the README (long documentation text)

That means GitHub is **not** serving your Vite `dist` folder; it is serving a **Jekyll / default static** build (often from the whole repository, like GitHub’s suggested workflow with `path: '.'`).

1. Go to **[Pages settings](https://github.com/Nabeel5160/Chatbot/settings/pages)**.
2. **Build and deployment → Source:** **GitHub Actions**.
3. Click **Configure** (or **Visit workflow**) and ensure the workflow tied to Pages is **`Deploy Vite app to Pages`** (file **`.github/workflows/pages.yml`**), **not** “Deploy static content to Pages” or any workflow that uploads the **entire repo**.
4. In **Actions**, delete or disable any extra workflow that deploys Pages from `.` (repository root).
5. Re-run **Deploy Vite app to Pages** on `main`.

The deployed site must load **`index.html` from `frontend/dist`** (React root + `/Chatbot/assets/...` scripts). This repo’s workflow adds **`.nojekyll`** so GitHub does not run Jekyll on your static files.

---

## 3) Frontend (Netlify)

1. Go to [netlify.com](https://netlify.com) → **Add new site** → **Import from Git** → pick **`Nabeel5160/Chatbot`**.
2. Set:
   - **Base directory:** `frontend`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend/dist`
3. Under **Site configuration → Environment variables**, add:
   - `VITE_API_BASE_URL` = your Render API URL **without** a trailing slash, e.g. `https://ogdcl-rag-api.onrender.com`
4. Redeploy after saving env vars.

Netlify will assign a URL like `https://random-name-123.netlify.app`. Use that as your **public app URL**.

---

## 4) CORS

If the browser blocks requests, set on the **API** host:

`CORS_ORIGINS=https://your-site.vercel.app` or `https://your-site.netlify.app`

(match exactly, including `https://`). Then restart the API service.

---

## 5) Alternatives

- **Railway / Fly.io:** also support Docker; set `PORT` if the platform injects it (Render does; the `Dockerfile` respects `PORT`).
- **Cloudflare Pages:** same as Netlify: build `frontend`, set `VITE_API_BASE_URL` to the API origin.

---

## 6) After deploy

1. Open the **frontend URL**.
2. Run **Upload & Index** once (or call `POST /upload` on the API) so Chroma is populated on that host.
3. Ask a question.

Your live URLs are always the ones shown in the **Render** and **Vercel** / **Netlify** dashboards after you deploy.
