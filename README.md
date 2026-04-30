# RAG Chatbot (NYSE PDF + ChatbotDocument TXT)

Production-oriented Retrieval Augmented Generation (RAG) chatbot built with FastAPI, LangChain, OpenAI, and local Chroma.

**Source repository:** [https://github.com/Nabeel5160/Chatbot.git](https://github.com/Nabeel5160/Chatbot.git)  
*Last sync: routine push from development environment.*

## Features

- PDF ingestion for `NYSE_KO_2024.pdf` and **plain-text** ingestion for `ChatbotDocument.txt` (SEC-style 10-K text)
- Chunking with overlap and metadata enrichment
- Batch embedding generation with persistent SQLite cache
- Local vector storage using Chroma
- Top-5 semantic retrieval
- Hybrid retrieval reranking (semantic + keyword overlap)
- Strict grounded GPT-4 answer generation
- Fallback response when information is missing:
  - `Information not found in the document.`
- Conversational API with session-aware history
- Citations with page + document; for TXT chunks, optional **section** and **line_start** / **line_end**
- Health and readiness endpoints
- Streaming chat endpoint (`/chat/stream`)
- Optional Streamlit UI
- Retrieval evaluation script

## Project Structure

```text
rag-chatbot/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── ingestion.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── retriever.py
│   ├── rag_chain.py
│   ├── api.py
│   └── errors.py
├── data/
│   └── NYSE_KO_2024.pdf
├── chroma_db/
├── requirements.txt
└── README.md
```

## Setup

1. Create virtual environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Create `.env` in project root (for example `Copy-Item .env.example .env` then edit `OPENAI_API_KEY`):

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=nyse_ko_2024
CHUNK_SIZE=2800
CHUNK_OVERLAP=400
TOP_K=5
SIMILARITY_THRESHOLD=0.2
EMBEDDING_BATCH_SIZE=32
MAX_HISTORY_TURNS=6
REQUEST_TIMEOUT_SECONDS=90

# Optional: default to the large TXT corpus and tune TXT chunking (character targets)
DEFAULT_DOCUMENT_TYPE=txt
DEFAULT_TEXT_DOCUMENT_PATH=./ChatbotDocument.txt
DEFAULT_TEXT_DOCUMENT_NAME=ChatbotDocument
TEXT_CHUNK_SIZE_CHARS=3200
TEXT_CHUNK_OVERLAP_CHARS=640
TXT_TAIL_EXCLUSION_MARKERS=POWER OF ATTORNEY,EXHIBIT 31.,EXHIBIT 32.
```

3. Documents:
   - Put `NYSE_KO_2024.pdf` in `data/` (recommended), or use `./NYSE_KO_2024.pdf`.
   - Put `ChatbotDocument.txt` in the project root (or set `DEFAULT_TEXT_DOCUMENT_PATH`). With `DEFAULT_DOCUMENT_TYPE=txt`, upload/chat defaults target this file when no path is given.

### ChatbotDocument.txt quick path

1. Set `OPENAI_API_KEY` and optionally the env block above.
2. Start the API, then ingest:

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/upload" `
  -F "document_path=./ChatbotDocument.txt" `
  -F "document_name=ChatbotDocument" `
  -F "rebuild_index=true"
```

3. Ask questions; sources may include `section`, `line_start`, and `line_end` instead of `page`.

#### Trial / free tier: demo without embedding quota

OpenAI **Embeddings** (used for semantic search) are billed separately from **chat**. If you see `429 insufficient_quota` on retrieval but still have **chat** credits (e.g. in Playground), set in `.env`:

`RAG_DEMO_LEXICAL_ONLY=true`

Restart the API. Search becomes **keyword overlap** over the same chunked text as production (`ChatbotDocument.txt` from `DEFAULT_TEXT_DOCUMENT_PATH`); **no `POST /upload` is required** for that mode. Answers still use `OPENAI_CHAT_MODEL` for generation. Semantic quality is lower than Chroma; for production, add billing and use embeddings + normal upload.

**Sanity questions** (answers should be grounded in the file; adjust wording to match your filing):

- Operating segments or reportable segments
- Material risks (often under Item 1A)
- Forward-looking statements or cautionary language
- Approximate market value of stock held by non-affiliates (if disclosed)
- Something clearly absent from the filing → expect the grounded fallback: `Information not found in the document.`

With a live API and key, run from repo root:

`powershell -ExecutionPolicy Bypass -File .\scripts\smoke_chatbot_document.ps1`

The script reads `OPENAI_API_KEY` from the environment or from `.env`, calls `GET /ready` (exit **3** if the API was started without a key—restart `uvicorn` after fixing), runs `POST /upload` with a long timeout, then five plan-style questions (the last must return the grounded fallback). Exits: **0** ok, **1** failed check, **2** no key, **3** not ready.

## Run

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### 1) Upload + Ingest Document

`POST /upload` (`multipart/form-data`)

Supported fields:
- `file` (optional): upload a PDF or TXT file
- `document_path` (optional): existing path on disk
- `document_name` (optional): logical document name
- `rebuild_index` (optional): `true/false`

Example using existing path:

```powershell
curl -X POST "http://localhost:8000/upload" `
  -F "document_path=./data/NYSE_KO_2024.pdf" `
  -F "document_name=NYSE_KO_2024" `
  -F "rebuild_index=true"
```

### 2) Chat

`POST /chat`

Request body:

```json
{
  "question": "What was Coca-Cola revenue in 2024?",
  "session_id": "user-1"
}
```

Response:

```json
{
  "answer": "...",
  "sources": [
    {
      "page": 12,
      "document": "NYSE_KO_2024",
      "section": null,
      "line_start": null,
      "line_end": null
    }
  ]
}
```

### 3) Health

- `GET /health`
- `GET /ready`

### 4) Streaming Chat (SSE)

`POST /chat/stream`

Returns structured `text/event-stream` events:
- `event: token` with `{"token":"..."}`
- `event: sources` with `{"sources":[...]}`
- `event: done` with `{"status":"done"}`

## Example Queries

- `What was Coca-Cola revenue in 2024?`
- `What risks did the company highlight for 2024?`
- `What was operating margin trend?`
- `Summarize management commentary for the year.`

If the answer is absent from the document, the system returns:

`Information not found in the document.`

## Notes

- Retrieval is semantic top-k (`k=5`) over Chroma.
- Metadata for every chunk includes `document`, `chunk_id`, and either `page` (PDF) or `section` + `line_start` / `line_end` (TXT, `page` null).
- Embeddings are cached in SQLite at `./data/embedding_cache.sqlite3`.
- Hybrid score uses `HYBRID_ALPHA` (default `0.7`) to blend vector and keyword scores.

## Bonus Tools

### Streamlit UI

```powershell
streamlit run streamlit_app.py
```

### Retrieval Evaluation

Create a dataset JSON like:

```json
[
  {
    "question": "What was Coca-Cola revenue in 2024?",
    "expected_pages": [12, 14]
  }
]
```

Run:

```powershell
python scripts/evaluate_retrieval.py --dataset eval_dataset.json
```

A ready sample dataset is included:

```powershell
python scripts/evaluate_retrieval.py --dataset eval_dataset.sample.json
```

### Endpoint Smoke Test Script (PowerShell)

Runs `/upload`, `/chat`, and `/chat/stream` in sequence:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_endpoints.ps1
```

With custom args:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_endpoints.ps1 `
  -BaseUrl "http://localhost:8000" `
  -DocumentPath "./data/NYSE_KO_2024.pdf" `
  -DocumentName "NYSE_KO_2024" `
  -Question "What was Coca-Cola revenue in 2024?" `
  -SessionId "my-session"
```

CI behavior:
- exits `0` when all checks pass
- exits `1` if any assertion fails (non-empty answer, valid sources array, SSE completion markers)

### Grounding Validator Tests

```powershell
pytest -q
```

### Deploy (free hosting)

See **[DEPLOY.md](./DEPLOY.md)** for **Render (API)** + **GitHub Pages**, **Vercel**, or **Netlify** (frontend), `VITE_API_BASE_URL`, and CORS. GitHub Pages URL for this repo: **`https://nabeel5160.github.io/Chatbot/`** (live after you enable Pages → GitHub Actions and set the `VITE_API_BASE_URL` variable). Source: [github.com/Nabeel5160/Chatbot](https://github.com/Nabeel5160/Chatbot).
