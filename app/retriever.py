import logging
import re
from typing import Any

from langchain_core.documents import Document

from app.config import Settings
from app.errors import RetrievalError
from app.ingestion import IngestionService
from app.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


class RetrieverService:
    def __init__(
        self,
        settings: Settings,
        vector_store_service: VectorStoreService,
        ingestion_service: IngestionService,
    ):
        self.settings = settings
        self.vector_store_service = vector_store_service
        self.ingestion_service = ingestion_service
        self._lexical_chunks: list[Document] | None = None
        self._lexical_logged = False

    def retrieve(self, question: str) -> dict[str, Any]:
        if self.settings.rag_demo_lexical_only:
            return self._lexical_retrieve(question)

        try:
            docs_with_scores = self.vector_store_service.similarity_search_with_score(
                query=question,
                k=self.settings.top_k,
            )
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            if "insufficient_quota" in detail or "429" in detail:
                detail = (
                    "OpenAI blocked the search step (embeddings) with insufficient_quota. "
                    "This is an account/billing limit, not your question wording—every question is embedded before "
                    "the document is searched. Add a payment method and ensure the Embeddings API has quota at "
                    "https://platform.openai.com/account/billing (same org as your API key). "
                    "For a no-embeddings trial demo, set RAG_DEMO_LEXICAL_ONLY=true in .env and restart the API. "
                    f"Raw error: {exc}"
                )
            raise RetrievalError(f"Retrieval failed: {detail}") from exc
        if not docs_with_scores:
            return {"documents": [], "sources": [], "scores": []}

        filtered: list[tuple[Document, float]] = [
            (doc, score)
            for doc, score in docs_with_scores
            if score >= self.settings.similarity_threshold
        ]

        if not filtered:
            logger.info("All retrieval scores below threshold=%s", self.settings.similarity_threshold)
            return {"documents": [], "sources": [], "scores": []}

        reranked = self._hybrid_rerank(question, filtered)
        documents = [doc for doc, _ in reranked]
        scores = [score for _, score in reranked]
        sources = self._unique_sources(documents)

        logger.info("Retrieved %s documents for query", len(documents))
        return {"documents": documents, "sources": sources, "scores": scores}

    def _lexical_retrieve(self, question: str) -> dict[str, Any]:
        """Keyword overlap over disk chunks—no OpenAI embeddings (trial / demo)."""
        if not self._lexical_logged:
            logger.warning(
                "RAG_DEMO_LEXICAL_ONLY: keyword-only retrieval; embedding API is not used for search."
            )
            self._lexical_logged = True

        try:
            if self._lexical_chunks is None:
                self._lexical_chunks = self.ingestion_service.load_chunks_without_vectors()
        except Exception as exc:  # noqa: BLE001
            raise RetrievalError(f"Lexical demo retrieval failed to load chunks: {exc}") from exc

        q_terms = set(re.findall(r"\w+", question.lower()))
        if not q_terms:
            return {"documents": [], "sources": [], "scores": []}

        scored: list[tuple[Document, float]] = []
        for doc in self._lexical_chunks:
            d_terms = set(re.findall(r"\w+", doc.page_content.lower()))
            overlap = len(q_terms.intersection(d_terms))
            keyword_score = overlap / max(1, len(q_terms))
            scored.append((doc, keyword_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        nonzero = [(doc, score) for doc, score in scored if score > 0]
        if not nonzero:
            return {"documents": [], "sources": [], "scores": []}

        top = nonzero[: self.settings.top_k]
        documents = [doc for doc, _ in top]
        scores = [score for _, score in top]
        sources = self._unique_sources(documents)
        logger.info("Lexical demo retrieved %s documents for query", len(documents))
        return {"documents": documents, "sources": sources, "scores": scores}

    def _hybrid_rerank(
        self,
        question: str,
        docs_with_scores: list[tuple[Document, float]],
    ) -> list[tuple[Document, float]]:
        if not docs_with_scores:
            return docs_with_scores

        q_terms = set(re.findall(r"\w+", question.lower()))
        if not q_terms:
            return docs_with_scores

        alpha = max(0.0, min(1.0, self.settings.hybrid_alpha))
        reranked: list[tuple[Document, float]] = []
        for doc, semantic_score in docs_with_scores:
            d_terms = set(re.findall(r"\w+", doc.page_content.lower()))
            overlap = len(q_terms.intersection(d_terms))
            keyword_score = overlap / max(1, len(q_terms))
            hybrid_score = alpha * semantic_score + (1 - alpha) * keyword_score
            reranked.append((doc, hybrid_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked[: self.settings.top_k]

    @staticmethod
    def _unique_sources(documents: list[Document]) -> list[dict[str, Any]]:
        unique = {}
        for doc in documents:
            key = (
                doc.metadata.get("page"),
                doc.metadata.get("document"),
                doc.metadata.get("section"),
                doc.metadata.get("line_start"),
                doc.metadata.get("line_end"),
            )
            unique[key] = {
                "page": doc.metadata.get("page"),
                "document": doc.metadata.get("document"),
                "section": doc.metadata.get("section"),
                "line_start": doc.metadata.get("line_start"),
                "line_end": doc.metadata.get("line_end"),
            }
        return list(unique.values())
