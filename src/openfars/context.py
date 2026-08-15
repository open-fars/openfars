from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .config import OpenFARSConfig
from .workspace import Workspace


class ContextStore:
    """Typed, bounded stage handoffs; chat transcripts are never the source of truth."""

    def __init__(self, config: OpenFARSConfig, workspace: Workspace):
        self.config = config
        self.workspace = workspace
        self.workspace.path("handoffs").mkdir(parents=True, exist_ok=True)

    def pack(
        self,
        agent: str,
        instruction: str,
        artifacts: Sequence[str],
        *,
        open_questions: Optional[Sequence[str]] = None,
    ) -> str:
        budget = self.config.agent(agent).context_budget_chars
        header = {
            "schema": "openfars.context/v1",
            "project_id": self.workspace.project_id,
            "receiving_agent": agent,
            "instruction": instruction,
            "artifacts": list(artifacts),
            "open_questions": list(open_questions or []),
        }
        sections = ["OPENFARS CONTEXT ENVELOPE", json.dumps(header, ensure_ascii=False, indent=2)]
        remaining = max(0, budget - sum(len(section) for section in sections))
        available = [artifact for artifact in artifacts if self.workspace.path(artifact).exists()]
        per_artifact = max(1000, remaining // max(1, len(available)))
        for artifact in available:
            raw = self.workspace.read_text(artifact)
            content = _bounded(raw, per_artifact)
            digest = hashlib.sha256(raw.encode()).hexdigest()
            sections.extend(
                [
                    f"ARTIFACT {artifact} sha256={digest}",
                    content,
                ]
            )
        sections.extend(["TASK", instruction])
        return "\n\n".join(sections)

    def handoff(
        self,
        *,
        sequence: int,
        agent: str,
        stage: str,
        summary: str,
        produced: Sequence[str],
        next_agent: Optional[str],
        evidence_refs: Optional[Sequence[str]] = None,
        decisions: Optional[Mapping[str, Any]] = None,
        open_questions: Optional[Sequence[str]] = None,
    ) -> Path:
        artifacts = []
        for relative in produced:
            path = self.workspace.path(relative)
            if not path.exists():
                continue
            raw = path.read_bytes()
            artifacts.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
            )
        record: Dict[str, Any] = {
            "schema": "openfars.handoff/v1",
            "time": datetime.now(timezone.utc).isoformat(),
            "sequence": sequence,
            "agent": agent,
            "stage": stage,
            "summary": summary,
            "next_agent": next_agent,
            "artifacts": artifacts,
            "evidence_refs": list(evidence_refs or []),
            "decisions": dict(decisions or {}),
            "open_questions": list(open_questions or []),
        }
        path = self.workspace.write_json(f"handoffs/{sequence:02d}-{agent}-{stage}.json", record)
        self.workspace.append_event(
            "agent.handoff",
            {
                "agent": agent,
                "stage": stage,
                "next_agent": next_agent,
                "artifacts": [item["path"] for item in artifacts],
            },
        )
        return path


def _bounded(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.72)
    tail = max(0, limit - head - 120)
    return (
        text[:head]
        + "\n... [context clipped; full artifact remains in workspace] ...\n"
        + text[-tail:]
    )
