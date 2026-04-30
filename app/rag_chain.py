import logging
from collections import defaultdict
from collections.abc import Generator
import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.errors import GenerationError
from app.retriever import RetrieverService

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = "Information not found in the document."
MIN_TOKEN_LEN = 4
MIN_OVERLAP_COUNT = 2


def is_answer_grounded(answer: str, context: str) -> bool:
    answer_text = (answer or "").strip()
    context_text = (context or "").strip()
    if not answer_text:
        return False
    if answer_text.lower() == FALLBACK_ANSWER.lower():
        return True
    if not context_text:
        return False

    answer_tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9]+", answer_text.lower())
        if len(token) >= MIN_TOKEN_LEN
    }
    context_tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9]+", context_text.lower())
        if len(token) >= MIN_TOKEN_LEN
    }
    overlap = answer_tokens.intersection(context_tokens)
    if len(overlap) < MIN_OVERLAP_COUNT:
        return False

    answer_numbers = re.findall(r"\d[\d,\.]*", answer_text)
    if answer_numbers:
        return any(number in context_text for number in answer_numbers)
    return True


class RAGChainService:
    def __init__(self, settings: Settings, retriever_service: RetrieverService):
        self.settings = settings
        self.retriever_service = retriever_service
        self.llm = ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout_seconds,
            temperature=0,
        )
        self.prompt = ChatPromptTemplate.from_template(
            """
You are a strict document QA assistant.
Answer only from the provided context.
Do not use outside knowledge.
Include concise citations based on provided metadata (section and line range when available).
If the answer is missing in context, respond exactly with:
Information not found in the document.

Conversation history (for reference only):
{history}

Context:
{context}

Question:
{question}
"""
        )
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)

    def answer_question(self, question: str, session_id: str = "default") -> dict[str, Any]:
        retrieval = self.retriever_service.retrieve(question)
        docs: list[Document] = retrieval["documents"]
        sources = retrieval["sources"]

        if not docs:
            self._append_history(session_id, question, FALLBACK_ANSWER)
            return {"answer": FALLBACK_ANSWER, "sources": []}

        history_text = self._history_to_text(session_id)
        context_text = self._docs_to_context(docs)
        try:
            response = self.llm.invoke(
                self.prompt.format_messages(
                    history=history_text,
                    context=context_text,
                    question=question,
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise GenerationError(f"LLM generation failed: {exc}") from exc
        answer = (response.content or "").strip()
        if not answer:
            answer = FALLBACK_ANSWER
        if not is_answer_grounded(answer, context_text):
            logger.info("Generated answer failed grounding validator; using fallback.")
            answer = FALLBACK_ANSWER

        if answer.lower() == FALLBACK_ANSWER.lower():
            sources = []

        self._append_history(session_id, question, answer)
        return {"answer": answer, "sources": sources}

    def answer_question_stream(
        self,
        question: str,
        session_id: str = "default",
    ) -> tuple[Generator[str, None, None], dict[str, list[dict[str, Any]]]]:
        retrieval = self.retriever_service.retrieve(question)
        docs: list[Document] = retrieval["documents"]
        sources = retrieval["sources"]

        if not docs:
            answer = FALLBACK_ANSWER
            self._append_history(session_id, question, answer)

            def fallback_gen() -> Generator[str, None, None]:
                yield answer

            return fallback_gen(), {"sources": []}

        history_text = self._history_to_text(session_id)
        context_text = self._docs_to_context(docs)
        messages = self.prompt.format_messages(
            history=history_text,
            context=context_text,
            question=question,
        )

        stream_state: dict[str, list[dict[str, Any]]] = {"sources": sources}

        def token_gen() -> Generator[str, None, None]:
            full_answer = ""
            try:
                for chunk in self.llm.stream(messages):
                    token = chunk.content or ""
                    full_answer += token
                    if token:
                        yield token
            except Exception as exc:  # noqa: BLE001
                raise GenerationError(f"LLM streaming failed: {exc}") from exc
            final_answer = full_answer.strip() or FALLBACK_ANSWER
            if not is_answer_grounded(final_answer, context_text):
                logger.info("Streamed answer failed grounding validator; using fallback.")
                final_answer = FALLBACK_ANSWER
                stream_state["sources"] = []
            self._append_history(session_id, question, final_answer)

        return token_gen(), stream_state

    def _docs_to_context(self, docs: list[Document]) -> str:
        chunks = []
        for doc in docs:
            page = doc.metadata.get("page", "unknown")
            document = doc.metadata.get("document", "unknown")
            chunk_id = doc.metadata.get("chunk_id", "unknown")
            section = doc.metadata.get("section", "unknown")
            line_start = doc.metadata.get("line_start", "unknown")
            line_end = doc.metadata.get("line_end", "unknown")
            chunks.append(
                "[document="
                f"{document} page={page} section={section} line_start={line_start} "
                f"line_end={line_end} chunk={chunk_id}]\n{doc.page_content}"
            )
        return "\n\n".join(chunks)

    def _history_to_text(self, session_id: str) -> str:
        turns = self._history.get(session_id, [])
        if not turns:
            return "No previous conversation."
        return "\n".join(
            [f"User: {turn['question']}\nAssistant: {turn['answer']}" for turn in turns]
        )

    def _append_history(self, session_id: str, question: str, answer: str) -> None:
        turns = self._history[session_id]
        turns.append({"question": question, "answer": answer})
        self._history[session_id] = turns[-self.settings.max_history_turns :]
