import logging
import re
import time
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings
from app.embeddings import EmbeddingService
from app.errors import IngestionError
from app.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        embeddings_service: EmbeddingService,
        vector_store_service: VectorStoreService,
    ):
        self.settings = settings
        self.embeddings_service = embeddings_service
        self.vector_store_service = vector_store_service
        self.text_chunk_size = settings.text_chunk_size_chars
        self.text_chunk_overlap = settings.text_chunk_overlap_chars
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def _resolve_document_path(self, document_path: str | None) -> Path:
        if document_path:
            return Path(document_path)
        if self.settings.default_document_type.lower() == "txt":
            default_text_path = self.settings.text_document_path
            if default_text_path.exists():
                return default_text_path
        default_pdf_path = self.settings.document_path
        if default_pdf_path.exists():
            return default_pdf_path
        root_fallback = Path("./NYSE_KO_2024.pdf")
        if root_fallback.exists():
            return root_fallback
        text_fallback = Path("./ChatbotDocument.txt")
        if text_fallback.exists():
            return text_fallback
        return root_fallback

    def ingest_document(
        self,
        document_path: str | None = None,
        document_name: str | None = None,
        rebuild_index: bool = False,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        source_path = self._resolve_document_path(document_path)
        if not source_path.exists():
            raise IngestionError(f"Document not found: {source_path}")

        if rebuild_index:
            self.vector_store_service.reset_collection()

        output_document_name = document_name or self._default_doc_name_for_path(source_path)
        chunks = self._load_and_chunk(source_path=source_path, document_name=output_document_name)
        if not chunks:
            raise IngestionError("No text chunks could be extracted from the input document.")

        try:
            embeddings = self.embeddings_service.embed_texts([chunk.page_content for chunk in chunks])
        except RuntimeError as exc:
            raise IngestionError(
                "Embedding failed (check OpenAI billing, quota, and model access). "
                f"Details: {exc}"
            ) from exc
        ids = [chunk.metadata["chunk_id"] for chunk in chunks]
        try:
            self.vector_store_service.add_documents(chunks, ids=ids, embeddings=embeddings)
        except Exception as exc:  # noqa: BLE001
            raise IngestionError(f"Failed to persist vectors: {exc}") from exc

        duration = round(time.perf_counter() - started, 3)
        logger.info(
            "Ingestion complete | units=%s chunks=%s duration=%ss",
            self._source_unit_count(chunks),
            len(chunks),
            duration,
        )
        return {
            "document": output_document_name,
            "path": str(source_path),
            "pages": self._source_unit_count(chunks),
            "chunks": len(chunks),
            "vectors": len(chunks),
            "duration_seconds": duration,
        }

    def load_chunks_without_vectors(
        self,
        document_path: str | None = None,
        document_name: str | None = None,
    ) -> list[Document]:
        """Same chunking as ingest, without embeddings or vector store (for lexical-only demo retrieval)."""
        source_path = self._resolve_document_path(document_path)
        if not source_path.exists():
            raise IngestionError(f"Document not found: {source_path}")
        output_document_name = document_name or self._default_doc_name_for_path(source_path)
        chunks = self._load_and_chunk(source_path=source_path, document_name=output_document_name)
        if not chunks:
            raise IngestionError("No text chunks could be extracted from the input document.")
        return chunks

    def _default_doc_name_for_path(self, source_path: Path) -> str:
        if source_path.suffix.lower() == ".txt":
            return self.settings.default_text_document_name
        return self.settings.default_document_name

    def _load_and_chunk(self, source_path: Path, document_name: str) -> list[Document]:
        suffix = source_path.suffix.lower()
        if suffix == ".txt":
            return self._chunk_text_document(source_path, document_name)
        if suffix == ".pdf":
            pdf_loader = PyPDFLoader(str(source_path))
            pages = pdf_loader.load()
            if not pages:
                raise IngestionError("No text could be extracted from the PDF.")
            return self._chunk_pages(pages, document_name)
        raise IngestionError(f"Unsupported document type: {source_path.suffix}")

    def _source_unit_count(self, chunks: list[Document]) -> int:
        values: set[int] = set()
        for chunk in chunks:
            page = chunk.metadata.get("page")
            line_start = chunk.metadata.get("line_start")
            if isinstance(page, int):
                values.add(page)
            elif isinstance(line_start, int):
                values.add(line_start)
        return len(values)

    def _chunk_pages(self, pages: list[Document], document_name: str) -> list[Document]:
        output_chunks: list[Document] = []
        for page_doc in pages:
            page_number = int(page_doc.metadata.get("page", 0)) + 1
            split_docs = self.splitter.create_documents([page_doc.page_content])
            for chunk_index, split_doc in enumerate(split_docs):
                chunk_id = f"{document_name}_p{page_number}_c{chunk_index}"
                output_chunks.append(
                    Document(
                        page_content=split_doc.page_content.strip(),
                        metadata={
                            "page": page_number,
                            "document": document_name,
                            "chunk_id": chunk_id,
                        },
                    )
                )
        return [chunk for chunk in output_chunks if chunk.page_content]

    def _chunk_text_document(self, source_path: Path, document_name: str) -> list[Document]:
        raw_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        cleaned_lines = self._clean_text_lines(raw_lines)
        sections = self._split_sections(cleaned_lines)

        chunks: list[Document] = []
        for section_index, section in enumerate(sections):
            section_title = section["section"]
            lines = section["lines"]
            line_numbers = section["line_numbers"]
            chunk_lines: list[str] = []
            chunk_line_numbers: list[int] = []
            current_chars = 0
            chunk_index = 0

            for line, line_number in zip(lines, line_numbers, strict=True):
                chunk_lines.append(line)
                chunk_line_numbers.append(line_number)
                current_chars += len(line) + 1

                if current_chars >= self.text_chunk_size:
                    chunks.append(
                        self._build_text_chunk(
                            chunk_lines,
                            chunk_line_numbers,
                            document_name,
                            section_title,
                            section_index,
                            chunk_index,
                        )
                    )
                    overlap_chars = 0
                    overlap_lines: list[str] = []
                    overlap_numbers: list[int] = []
                    for back_line, back_num in zip(
                        reversed(chunk_lines), reversed(chunk_line_numbers), strict=True
                    ):
                        overlap_chars += len(back_line) + 1
                        overlap_lines.insert(0, back_line)
                        overlap_numbers.insert(0, back_num)
                        if overlap_chars >= self.text_chunk_overlap:
                            break
                    chunk_lines = overlap_lines
                    chunk_line_numbers = overlap_numbers
                    current_chars = sum(len(x) + 1 for x in chunk_lines)
                    chunk_index += 1

            if chunk_lines:
                chunks.append(
                    self._build_text_chunk(
                        chunk_lines,
                        chunk_line_numbers,
                        document_name,
                        section_title,
                        section_index,
                        chunk_index,
                    )
                )
        return chunks

    def _build_text_chunk(
        self,
        chunk_lines: list[str],
        chunk_line_numbers: list[int],
        document_name: str,
        section_title: str,
        section_index: int,
        chunk_index: int,
    ) -> Document:
        line_start = chunk_line_numbers[0]
        line_end = chunk_line_numbers[-1]
        chunk_id = f"{document_name}_s{section_index}_c{chunk_index}_l{line_start}_{line_end}"
        content = "\n".join(chunk_lines).strip()
        return Document(
            page_content=content,
            metadata={
                "document": document_name,
                "chunk_id": chunk_id,
                "section": section_title,
                "line_start": line_start,
                "line_end": line_end,
                "page": None,
            },
        )

    def _clean_text_lines(self, lines: list[str]) -> list[tuple[int, str]]:
        cleaned: list[tuple[int, str]] = []
        remove_tail_markers = self.settings.txt_tail_markers_tuple
        tail_mode = False

        for idx, line in enumerate(lines, start=1):
            normalized = re.sub(r"[ \t]+", " ", line).strip()
            if not normalized:
                continue
            if re.fullmatch(r"\d+", normalized):
                continue
            if any(marker in normalized for marker in remove_tail_markers):
                tail_mode = True
            if tail_mode:
                continue
            cleaned.append((idx, normalized))
        return cleaned

    def _split_sections(self, cleaned_lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
        section_pattern = re.compile(r"^(ITEM\s+\d+[A-Z]?\.?|PART\s+[IVX]+)\b", re.IGNORECASE)
        sections: list[dict[str, Any]] = []
        current_section = "FRONT_MATTER"
        lines: list[str] = []
        line_numbers: list[int] = []

        for line_number, line in cleaned_lines:
            if section_pattern.match(line):
                if lines:
                    sections.append(
                        {
                            "section": current_section,
                            "lines": lines,
                            "line_numbers": line_numbers,
                        }
                    )
                current_section = line
                lines = [line]
                line_numbers = [line_number]
                continue
            lines.append(line)
            line_numbers.append(line_number)

        if lines:
            sections.append(
                {"section": current_section, "lines": lines, "line_numbers": line_numbers}
            )
        return sections
