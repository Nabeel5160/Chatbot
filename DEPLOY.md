# Deploying the OGDCL RAG app (free tier)

Canonical GitHub repo: **[https://github.com/Nabeel5160/Chatbot](https://github.com/Nabeel5160/Chatbot)**  
Clone: `git clone https://github.com/Nabeel5160/Chatbot.git`

This repo cannot be deployed for you from Cursor: **you** create the accounts and paste the URLs you get (for example `https://ogdcl-rag-api.onrender.com` and `https://your-site.netlify.app`).

Recommended split: **API on Render (Docker)** · **static UI on Netlify or Cloudflare Pages**.

---

## 1) Backend (Render)

1. Use the GitHub repo above (include `ChatbotDocument.txt` in the default branch if you want the corpus baked into the Docker image).
2. Go to [render.com](https://render.com) → **New +** → **Web Service** → connect **`Nabeel5160/Chatbot`**.
3. Choose **Docker** (uses the root `Dockerfile`).
4. Set environment variables (same as local `.env`), at minimum:
   - `OPENAI_API_KEY`
   - Optional: `CORS_ORIGINS` — set to your **frontend** URL(s), comma-separated, e.g. `https://your-app.netlify.app` (safer than `*`).
5. Deploy. Copy the service URL, e.g. `https://ogdcl-rag-api.onrender.com`.

**Free tier notes:** The service **spins down when idle** (first request after sleep can take ~1 minute). `chroma_db` on the default disk is **ephemeral** unless you add a paid disk — re-run **Upload & Index** after cold starts if vectors are lost.

---

## 2) Frontend (Netlify)

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

## 3) CORS

If the browser blocks requests, set on the **API** host:

`CORS_ORIGINS=https://your-site.netlify.app`

(match exactly, including `https://`). Then restart the API service.

---

## Alternatives

- **Railway / Fly.io:** also support Docker; set `PORT` if the platform injects it (Render does; the `Dockerfile` respects `PORT`).
- **Cloudflare Pages:** same as Netlify: build `frontend`, set `VITE_API_BASE_URL` to the API origin.

---

## After deploy

1. Open the **frontend URL**.
2. Run **Upload & Index** once (or call `POST /upload` on the API) so Chroma is populated on that host.
3. Ask a question.

Your live URLs are always the ones shown in the **Render** and **Netlify** (or Pages) dashboards after you deploy.
