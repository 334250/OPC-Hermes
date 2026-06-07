"""Artifact Manager for OPC-Hermes.

Manages worker output files with versioning, directory structure,
and metadata tracking.

Directory layout:
  ~/.hermes/opc/artifacts/
    <task_id>/
      <worker_id>/
        v001/
          output.ext
          metadata.json
        v002/
          output.ext
          metadata.json
        latest → v002/

Design reference: §9.10 产物管理 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ArtifactManager:
    """Manages versioned artifacts produced by Worker agents."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            try:
                from hermes_constants import get_hermes_home
                base_dir = get_hermes_home() / "opc" / "artifacts"
            except ImportError:
                base_dir = Path.home() / ".hermes" / "opc" / "artifacts"
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ── Path helpers ─────────────────────────────────────────────────────

    def _task_dir(self, task_id: str) -> Path:
        return self._base_dir / task_id

    def _worker_dir(self, task_id: str, worker_id: str) -> Path:
        return self._task_dir(task_id) / worker_id

    def _version_dir(self, task_id: str, worker_id: str, version: int) -> Path:
        return self._worker_dir(task_id, worker_id) / f"v{version:03d}"

    def _latest_link(self, task_id: str, worker_id: str) -> Path:
        return self._worker_dir(task_id, worker_id) / "latest"

    # ── Store API ────────────────────────────────────────────────────────

    def store(
        self,
        task_id: str,
        worker_id: str,
        file_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a worker output file with versioning.

        Args:
            task_id: The task this artifact belongs to.
            worker_id: The worker that produced it.
            file_path: Path to the file to store (copied in).
            metadata: Optional metadata dict (stored as metadata.json).

        Returns:
            Dict with {version, stored_path, metadata_path}.
        """
        version = self._next_version(task_id, worker_id)
        version_dir = self._version_dir(task_id, worker_id, version)
        version_dir.mkdir(parents=True, exist_ok=True)

        # Copy the output file
        dest = version_dir / file_path.name
        shutil.copy2(file_path, dest)

        # Write metadata
        meta = {
            "task_id": task_id,
            "worker_id": worker_id,
            "version": version,
            "original_name": file_path.name,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "file_size": dest.stat().st_size,
            **(metadata or {}),
        }
        meta_path = version_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Update latest symlink
        latest = self._latest_link(task_id, worker_id)
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(version_dir.name, target_is_directory=True)

        logger.info(
            "Stored artifact: %s (v%03d, %d bytes)",
            dest, version, dest.stat().st_size,
        )

        return {
            "version": version,
            "stored_path": str(dest),
            "metadata_path": str(meta_path),
        }

    # ── Retrieve API ─────────────────────────────────────────────────────

    def get_latest(self, task_id: str, worker_id: str) -> Optional[Path]:
        """Get the path to the latest version of a worker's output."""
        latest = self._latest_link(task_id, worker_id)
        if not latest.exists():
            return None
        # Resolve symlink
        resolved = latest.resolve()
        # Return the file inside (first non-metadata file)
        for entry in resolved.iterdir():
            if entry.name != "metadata.json":
                return entry
        return None

    def list_versions(self, task_id: str, worker_id: str) -> List[Dict[str, Any]]:
        """List all versions of a worker's output for a task."""
        worker_dir = self._worker_dir(task_id, worker_id)
        if not worker_dir.exists():
            return []

        versions = []
        for entry in sorted(worker_dir.iterdir()):
            if entry.is_dir() and entry.name.startswith("v"):
                meta_file = entry / "metadata.json"
                meta = {}
                if meta_file.exists():
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                versions.append(meta)
        return versions

    def get_task_artifacts(self, task_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get all artifacts for a task, grouped by worker."""
        task_dir = self._task_dir(task_id)
        if not task_dir.exists():
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}
        for worker_entry in task_dir.iterdir():
            if worker_entry.is_dir():
                result[worker_entry.name] = self.list_versions(task_id, worker_entry.name)
        return result

    # ── Internal ─────────────────────────────────────────────────────────

    def _next_version(self, task_id: str, worker_id: str) -> int:
        """Determine the next version number for a worker's output."""
        worker_dir = self._worker_dir(task_id, worker_id)
        if not worker_dir.exists():
            return 1

        max_version = 0
        for entry in worker_dir.iterdir():
            if entry.is_dir() and entry.name.startswith("v"):
                try:
                    v = int(entry.name[1:])
                    max_version = max(max_version, v)
                except ValueError:
                    pass
        return max_version + 1
