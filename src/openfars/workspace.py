from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class Workspace:
    """A project-local, append-audited artifact store."""

    def __init__(self, root: Path, project_id: str):
        if not project_id or project_id in {".", ".."} or "/" in project_id:
            raise ValueError("project_id must be one safe path segment")
        self.root = root.expanduser().resolve()
        self.project_id = project_id
        self.project_dir = (self.root / project_id).resolve()
        if self.project_dir.parent != self.root:
            raise ValueError("project_id escapes output directory")
        for child in ("artifacts", "code", "paper", "decisions", "sessions", "reports"):
            (self.project_dir / child).mkdir(parents=True, exist_ok=True)

    def path(self, relative: str | Path) -> Path:
        candidate = (self.project_dir / relative).resolve()
        try:
            candidate.relative_to(self.project_dir)
        except ValueError as error:
            raise ValueError(f"Path escapes project workspace: {relative}") from error
        return candidate

    def write_text(self, relative: str | Path, content: str) -> Path:
        destination = self.path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(destination, content)
        return destination

    def read_text(self, relative: str | Path, default: str = "") -> str:
        source = self.path(relative)
        return source.read_text(encoding="utf-8") if source.exists() else default

    def write_json(self, relative: str | Path, data: Any) -> Path:
        return self.write_text(
            relative,
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def read_json(self, relative: str | Path, default: Optional[Any] = None) -> Any:
        source = self.path(relative)
        if not source.exists():
            return default
        with source.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def append_event(self, event_type: str, data: Dict[str, Any]) -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        }
        destination = self.path("events.jsonl")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def list_files(self, relative: str | Path = ".") -> Iterable[Path]:
        directory = self.path(relative)
        if not directory.exists():
            return []
        return sorted(path for path in directory.rglob("*") if path.is_file())

    @staticmethod
    def _atomic_write(destination: Path, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(
            dir=str(destination.parent), prefix=f".{destination.name}.", text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
