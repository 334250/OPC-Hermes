"""
Knowledge Pipeline — populates the Knowledge Base from user uploads and crawls.

Two channels:
  1. User upload: parse documents (PDF, DOCX, Markdown, URLs, videos)
     → structured extraction → write to Knowledge Base
  2. Crawler: per-agent periodic crawl → dedup → quality score → write

The Knowledge Base is read-only for all agents (Leader, Worker, Evaluator).
Only the Knowledge Pipeline can write to it.

Design reference: §8.2-8.3 知识获取管道 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Supported source types ──────────────────────────────────────────────

SOURCE_TYPES = {
    "upload": "User-uploaded file",
    "url": "URL content extraction",
    "crawl": "Scheduled web crawl",
    "manual": "Manually entered knowledge",
    "import": "Batch import from external source",
}

# ── File parsers (stubs — Phase 4) ──────────────────────────────────────

_SUPPORTED_EXTENSIONS = {
    ".md": "markdown",
    ".txt": "text",
    ".pdf": "pdf",
    ".docx": "docx",
    ".html": "html",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
}


class KnowledgePipeline:
    """Populates the Knowledge Base from various sources."""

    def __init__(self, upload_dir: Optional[Path] = None):
        if upload_dir is None:
            try:
                from hermes_constants import get_hermes_home
                upload_dir = get_hermes_home() / "opc" / "uploads"
            except ImportError:
                upload_dir = Path.home() / ".hermes" / "opc" / "uploads"
        self._upload_dir = Path(upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    # ── User Upload Channel ──────────────────────────────────────────────

    def ingest_file(self, file_path: Path, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Parse a user-uploaded file and add it to the Knowledge Base.

        Args:
            file_path: Path to the file to ingest.
            tags: Optional tags for categorization.

        Returns:
            Dict with {entry_id, title, source_type, word_count}.
        """
        if not file_path.exists():
            return {"status": "error", "message": f"File not found: {file_path}"}

        ext = file_path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            return {
                "status": "error",
                "message": f"Unsupported file type: {ext}. Supported: {list(_SUPPORTED_EXTENSIONS.keys())}",
            }

        # Parse content
        content = self._parse_file(file_path)
        if not content:
            return {"status": "error", "message": f"Could not extract content from {file_path.name}"}

        # Write to Knowledge Base
        from opc_hermes.memory_layer.gated_memory import get_memory_layer
        memory = get_memory_layer()

        entry_id = memory.kb_add_entry(
            title=file_path.stem,
            content=content,
            source_url=str(file_path),
            source_type="upload",
            tags=tags or [],
        )

        logger.info("Ingested file: %s → KB entry %d (%d chars)", file_path.name, entry_id, len(content))

        return {
            "status": "ok",
            "entry_id": entry_id,
            "title": file_path.stem,
            "source_type": "upload",
            "word_count": len(content.split()),
            "char_count": len(content),
        }

    def ingest_url(self, url: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch and extract content from a URL, then add to Knowledge Base.

        In Phase 4, this uses web_extract (Firecrawl or equivalent).
        Phase 3 stub returns a placeholder.
        """
        # Phase 3 stub — full implementation in Phase 4 with web_extract.
        logger.info("[STUB] Would ingest URL: %s", url)

        return {
            "status": "stub",
            "message": "URL ingestion will be implemented in Phase 4 using web_extract.",
            "url": url,
        }

    def ingest_text(
        self, title: str, content: str, *,
        source_type: str = "manual", tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add manually entered text to the Knowledge Base."""
        from opc_hermes.memory_layer.gated_memory import get_memory_layer
        memory = get_memory_layer()

        entry_id = memory.kb_add_entry(
            title=title,
            content=content,
            source_type=source_type,
            tags=tags or [],
        )

        return {
            "status": "ok",
            "entry_id": entry_id,
            "title": title,
            "word_count": len(content.split()),
        }

    # ── Crawler Channel ──────────────────────────────────────────────────

    def run_crawl(self, agent_id: str) -> Dict[str, Any]:
        """Run a knowledge crawl for a specific agent's configured sources.

        In Phase 4, this will crawl URLs configured per-agent.
        Phase 3 stub.
        """
        logger.info("[STUB] Would run crawl for agent: %s", agent_id)
        return {
            "status": "stub",
            "message": f"Crawl for agent '{agent_id}' will be implemented in Phase 4.",
            "agent_id": agent_id,
        }

    # ── Query API ────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search the Knowledge Base."""
        from opc_hermes.memory_layer.gated_memory import get_memory_layer
        memory = get_memory_layer()
        return memory.kb_search(query, top_k=top_k)

    # ── Internal ─────────────────────────────────────────────────────────

    def _parse_file(self, file_path: Path) -> str:
        """Parse a file's content based on its extension."""
        ext = file_path.suffix.lower()

        if ext in (".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html"):
            try:
                return file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    return file_path.read_text(encoding="latin-1")
                except Exception:
                    return ""

        # PDF, DOCX parsing in Phase 4
        logger.debug("No parser yet for %s — returning empty (Phase 4)", ext)
        return f"[{ext} parsing not yet implemented — Phase 4]"
