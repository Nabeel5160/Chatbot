import logging
from typing import Any

import chromadb
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from app.config import Settings

logger = logging.getLogger(__name__)


class VectorStoreService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.chroma_dir_path.mkdir(parents=True, exist_ok=True)
        self._embedding_client = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._store = Chroma(
            client=self._client,
            collection_name=self.settings.chroma_collection_name,
            embedding_function=self._embedding_client,
            persist_directory=self.settings.chroma_persist_dir,
        )

    @property
    def store(self) -> Chroma:
        return self._store

    def reset_collection(self) -> None:
        try:
            self._client.delete_collection(self.settings.chroma_collection_name)
        except Exception:  # noqa: BLE001
            logger.info("Collection did not exist yet; creating new one.")
        self._store = Chroma(
            client=self._client,
            collection_name=self.settings.chroma_collection_name,
            embedding_function=self._embedding_client,
            persist_directory=self.settings.chroma_persist_dir,
        )

    def add_documents(
        self,
        documents: list[Document],
        ids: list[str],
        embeddings: list[list[float]],
    ) -> None:
        if not documents:
            return
        self._store.add_documents(documents=documents, ids=ids, embeddings=embeddings)

    def similarity_search_with_score(
        self,
        query: str,
        k: int,
    ) -> list[tuple[Document, float]]:
        return self._store.similarity_search_with_relevance_scores(query=query, k=k)

    def count(self) -> int:
        collection = self._client.get_or_create_collection(self.settings.chroma_collection_name)
        return collection.count()

    def as_metadata_summary(self, docs_with_scores: list[tuple[Document, float]]) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for doc, score in docs_with_scores:
            summary.append(
                {
                    "score": score,
                    "page": doc.metadata.get("page"),
                    "document": doc.metadata.get("document"),
                    "chunk_id": doc.metadata.get("chunk_id"),
                }
            )
        return summary
