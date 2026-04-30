import logging
from collections.abc import Generator
from functools import lru_cache
import json
from pathlib import Path
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.embeddings import EmbeddingService
from app.errors import ConfigurationError, GenerationError, IngestionError, RetrievalError
from app.ingestion import IngestionService
from app.rag_chain import RAGChainService
from app.retriever import RetrieverService
from app.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_filename(filename: str) -> str:
    safe_name = Path(filename).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)
    if not (safe_name.lower().endswith(".pdf") or safe_name.lower().endswith(".txt")):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are allowed.")
    return safe_name


def _validate_document_path(input_path: str, data_dir: str) -> str:
    candidate = Path(input_path).resolve()
    allowed_root = Path(data_dir).resolve()
    project_root = Path(".").resolve()
    allowed_paths = {allowed_root, project_root}
    if not any(root in candidate.parents or candidate == root for root in allowed_paths):
        raise HTTPException(
            status_code=400,
            detail="document_path must be within the project or configured data directory.",
        )
    if candidate.suffix.lower() not in {".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are allowed.")
    return str(candidate)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=get_settings().max_question_length)
    session_id: str = "default"


class SourceItem(BaseModel):
    page: int | None = None
    document: str | None = None
    section: str | None = None
    line_start: int | None = None
    line_end: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]


@lru_cache(maxsize=1)
def get_services() -> dict[str, object]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ConfigurationError("OPENAI_API_KEY is not configured.")
    vector_store = VectorStoreService(settings)
    embeddings = EmbeddingService(settings)
    ingestion = IngestionService(settings, embeddings, vector_store)
    retriever = RetrieverService(settings, vector_store, ingestion)
    rag_chain = RAGChainService(settings, retriever)
    return {
        "settings": settings,
        "vector_store": vector_store,
        "embeddings": embeddings,
        "ingestion": ingestion,
        "retriever": retriever,
        "rag_chain": rag_chain,
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, object]:
    try:
        services = get_services()
        settings = services["settings"]
        vector_store: VectorStoreService = services["vector_store"]  # type: ignore[assignment]
        return {
            "status": "ready",
            "openai_key_configured": bool(settings.openai_api_key),  # type: ignore[union-attr]
            "vector_count": vector_store.count(),
        }
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness check failed: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "Dependency check failed."},
        ) from exc


@router.post("/upload")
async def upload_document(
    file: UploadFile | None = File(default=None),
    document_path: str | None = Form(default=None),
    document_name: str | None = Form(default=None),
    rebuild_index: bool = Form(default=False),
) -> dict[str, object]:
    try:
        services = get_services()
        settings = services["settings"]  # type: ignore[assignment]
        ingestion: IngestionService = services["ingestion"]  # type: ignore[assignment]

        source_path = document_path
        if file is not None:
            target_dir = Path(settings.data_dir)  # type: ignore[union-attr]
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _sanitize_filename(file.filename or "uploaded.pdf")
            target_file = target_dir / safe_name
            with target_file.open("wb") as f:
                f.write(await file.read())
            source_path = str(target_file)
        elif document_path:
            source_path = _validate_document_path(document_path, settings.data_dir)  # type: ignore[arg-type]

        return ingestion.ingest_document(
            document_path=source_path,
            document_name=document_name,
            rebuild_index=rebuild_index,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IngestionError as exc:
        msg = str(exc)
        status = 404 if msg.startswith("Document not found:") else 503
        raise HTTPException(status_code=status, detail=msg) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Upload failed: %s", str(exc))
        raise HTTPException(status_code=500, detail="Upload failed.") from exc


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        services = get_services()
        rag_chain: RAGChainService = services["rag_chain"]  # type: ignore[assignment]
        result = rag_chain.answer_question(payload.question, session_id=payload.session_id)
        return ChatResponse(
            answer=result["answer"],
            sources=[SourceItem(**source) for source in result["sources"]],
        )
    except (RetrievalError, GenerationError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat failed: %s", str(exc))
        raise HTTPException(status_code=500, detail="Chat processing failed.") from exc


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    try:
        services = get_services()
        rag_chain: RAGChainService = services["rag_chain"]  # type: ignore[assignment]
        token_gen, stream_state = rag_chain.answer_question_stream(
            payload.question, session_id=payload.session_id
        )

        def event_stream() -> Generator[str, None, None]:
            for token in token_gen:
                payload = json.dumps({"token": token}, ensure_ascii=True)
                yield f"event: token\ndata: {payload}\n\n"
            sources_payload = json.dumps({"sources": stream_state["sources"]}, ensure_ascii=True)
            yield f"event: sources\ndata: {sources_payload}\n\n"
            yield "event: done\ndata: {\"status\":\"done\"}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except (RetrievalError, GenerationError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Streaming chat failed: %s", str(exc))
        raise HTTPException(status_code=500, detail="Streaming chat failed.") from exc
