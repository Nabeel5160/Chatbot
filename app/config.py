from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "NYSE KO 2024 RAG Chatbot"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Comma-separated browser origins for CORS, e.g. https://your-app.netlify.app
    # Use "*" only for quick demos (tighten for production).
    cors_origins: str = "*"

    openai_api_key: str = Field(default="")
    openai_chat_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"

    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "nyse_ko_2024"

    data_dir: str = "./data"
    default_document_path: str = "./data/NYSE_KO_2024.pdf"
    default_document_name: str = "NYSE_KO_2024"
    default_text_document_path: str = "./ChatbotDocument.txt"
    default_text_document_name: str = "ChatbotDocument"
    default_document_type: str = "txt"

    chunk_size: int = 2800
    chunk_overlap: int = 400
    top_k: int = 5
    max_history_turns: int = 6
    max_question_length: int = 1000

    embedding_batch_size: int = 32
    similarity_threshold: float = 0.2
    request_timeout_seconds: int = 90
    embedding_cache_db: str = "./data/embedding_cache.sqlite3"
    hybrid_alpha: float = 0.7

    # When true: skip Chroma/OpenAI embeddings for retrieval; rank chunks by keyword overlap only.
    # Use for trials with no embedding quota; chat (LLM) still calls OpenAI unless you use a local model elsewhere.
    rag_demo_lexical_only: bool = False

    # Large TXT corpus (e.g. SEC 10-K plain text): character targets ~600–750 token chunks, ~120 token overlap.
    text_chunk_size_chars: int = 3200
    text_chunk_overlap_chars: int = 640
    # Comma-separated substrings; lines containing any marker start tail exclusion until EOF.
    txt_tail_exclusion_markers: str = "POWER OF ATTORNEY,EXHIBIT 31.,EXHIBIT 32."

    @property
    def document_path(self) -> Path:
        return Path(self.default_document_path)

    @property
    def text_document_path(self) -> Path:
        return Path(self.default_text_document_path)

    @property
    def txt_tail_markers_tuple(self) -> tuple[str, ...]:
        parts = [p.strip() for p in self.txt_tail_exclusion_markers.split(",")]
        return tuple(m for m in parts if m)

    @property
    def chroma_dir_path(self) -> Path:
        return Path(self.chroma_persist_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
