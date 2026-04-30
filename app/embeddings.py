import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from langchain_openai import OpenAIEmbeddings

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        self._cache_path = Path(settings.embedding_cache_db)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_cache()

    def _init_cache(self) -> None:
        with sqlite3.connect(self._cache_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    text_hash TEXT PRIMARY KEY,
                    vector_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_cached_vector(self, text_hash: str) -> list[float] | None:
        with sqlite3.connect(self._cache_path) as conn:
            row = conn.execute(
                "SELECT vector_json FROM embedding_cache WHERE text_hash = ?",
                (text_hash,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def _save_cached_vectors(self, rows: Iterable[tuple[str, list[float]]]) -> None:
        with sqlite3.connect(self._cache_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO embedding_cache(text_hash, vector_json)
                VALUES (?, ?)
                """,
                [(text_hash, json.dumps(vector)) for text_hash, vector in rows],
            )
            conn.commit()

    def _embed_with_retry(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return self.client.embed_documents(texts)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                delay = attempt * 1.5
                logger.warning(
                    "Embedding batch failed (attempt=%s/%s): %s",
                    attempt,
                    retries,
                    str(exc),
                )
                time.sleep(delay)
        raise RuntimeError(f"Embedding batch failed after retries: {last_exc}")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        hashes = [self._hash_text(text) for text in texts]
        final_vectors: list[list[float] | None] = [None] * len(texts)
        misses: list[tuple[int, str, str]] = []

        for index, (text, text_hash) in enumerate(zip(texts, hashes, strict=True)):
            cached = self._get_cached_vector(text_hash)
            if cached is not None:
                final_vectors[index] = cached
            else:
                misses.append((index, text_hash, text))

        if misses:
            logger.info("Embedding cache misses: %s/%s", len(misses), len(texts))
            batch_size = max(1, self.settings.embedding_batch_size)
            rows_to_cache: list[tuple[str, list[float]]] = []
            for start in range(0, len(misses), batch_size):
                batch = misses[start : start + batch_size]
                batch_texts = [item[2] for item in batch]
                vectors = self._embed_with_retry(batch_texts)
                for (orig_index, text_hash, _), vector in zip(batch, vectors, strict=True):
                    final_vectors[orig_index] = vector
                    rows_to_cache.append((text_hash, vector))
            self._save_cached_vectors(rows_to_cache)

        return [vector for vector in final_vectors if vector is not None]

    def embed_query(self, query: str) -> list[float]:
        if not query:
            return []
        return self.client.embed_query(query)
