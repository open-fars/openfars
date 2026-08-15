from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

from .config import HumanConfig
from .workspace import Workspace


class HumanDecisionRequired(RuntimeError):
    def __init__(self, project_id: str, checkpoint: str):
        self.project_id = project_id
        self.checkpoint = checkpoint
        super().__init__(
            f"Human decision required: openfars decide {project_id} {checkpoint} --approve"
        )


@dataclass(frozen=True)
class Decision:
    action: str
    selected_id: Optional[str] = None
    feedback: str = ""
    overrides: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Decision":
        action = str(raw.get("action", "")).lower()
        if action not in {"approve", "reject"}:
            raise ValueError("Decision action must be approve or reject")
        overrides = raw.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("Decision overrides must be a JSON object")
        return cls(
            action=action,
            selected_id=raw.get("selected_id"),
            feedback=str(raw.get("feedback", "")),
            overrides=overrides,
        )


class HumanGate:
    """Asynchronous, file-backed checkpoints with deliberately compressed context."""

    def __init__(self, config: HumanConfig, workspace: Workspace):
        self.config = config
        self.workspace = workspace

    def decide(
        self,
        checkpoint: str,
        payload: Mapping[str, Any],
        *,
        default_selected_id: Optional[str] = None,
    ) -> Decision:
        if checkpoint not in self.config.checkpoints or self.config.mode == "off":
            return Decision("approve", selected_id=default_selected_id)

        decision_path = f"decisions/{checkpoint}.decision.json"
        existing = self.workspace.read_json(decision_path)
        if existing is not None:
            decision = Decision.from_dict(existing)
            self.workspace.append_event(
                "human.decision",
                {
                    "checkpoint": checkpoint,
                    "action": decision.action,
                    "has_feedback": bool(decision.feedback),
                    "has_overrides": bool(decision.overrides),
                },
            )
            return decision

        request = {
            "checkpoint": checkpoint,
            "project_id": self.workspace.project_id,
            "default_selected_id": default_selected_id,
            "allowed_actions": ["approve", "reject"],
            "payload": payload,
        }
        self.workspace.write_json(f"decisions/{checkpoint}.request.json", request)
        self.workspace.write_text(
            f"decisions/{checkpoint}.packet.md",
            render_packet(checkpoint, payload, default_selected_id),
        )
        self.workspace.append_event("human.requested", {"checkpoint": checkpoint})

        if self.config.mode == "cli" and sys.stdin.isatty():
            return self._ask_cli(checkpoint, default_selected_id)
        raise HumanDecisionRequired(self.workspace.project_id, checkpoint)

    def _ask_cli(self, checkpoint: str, default_selected_id: Optional[str]) -> Decision:
        packet = self.workspace.path(f"decisions/{checkpoint}.packet.md")
        print(f"\nHuman checkpoint: {checkpoint}\nDecision packet: {packet}")
        answer = input("Approve? [Y/n] ").strip().lower()
        action = "reject" if answer in {"n", "no"} else "approve"
        selected = input(f"Selected ID [{default_selected_id or ''}]: ").strip()
        feedback = input("Short steering feedback (optional): ").strip()
        decision = Decision(action, selected or default_selected_id, feedback)
        self.workspace.write_json(f"decisions/{checkpoint}.decision.json", asdict(decision))
        return decision


def write_decision(
    workspace: Workspace,
    checkpoint: str,
    *,
    action: str,
    selected_id: Optional[str] = None,
    feedback: str = "",
    overrides: Optional[Mapping[str, Any]] = None,
) -> None:
    request = workspace.path(f"decisions/{checkpoint}.request.json")
    if not request.exists():
        raise ValueError(f"No pending request for checkpoint '{checkpoint}'")
    decision = Decision.from_dict(
        {
            "action": action,
            "selected_id": selected_id,
            "feedback": feedback,
            "overrides": dict(overrides or {}),
        }
    )
    workspace.write_json(f"decisions/{checkpoint}.decision.json", asdict(decision))


def render_packet(
    checkpoint: str,
    payload: Mapping[str, Any],
    default_selected_id: Optional[str],
) -> str:
    lines = [
        f"# OpenFARS decision: {checkpoint}",
        "",
        "This packet contains the decision frontier, not the full agent transcript.",
        f"Default: `{default_selected_id}`"
        if default_selected_id
        else "Default: approve as written",
        "",
    ]
    if checkpoint == "idea":
        for index, candidate in enumerate(payload.get("candidates", []), start=1):
            lines.extend(
                [
                    f"## {index}. {candidate.get('title', 'Untitled')} (`{candidate.get('id', '')}`)",
                    "",
                    f"- Claim: {candidate.get('hypothesis', '')}",
                    f"- Decisive test: {candidate.get('test', '')}",
                    f"- Falsifier: {candidate.get('falsifier', '')}",
                    f"- Score: {candidate.get('composite', 0)}; judge disagreement: {candidate.get('judge_disagreement', 0)}",
                    f"- Evidence retrieved: {len(candidate.get('nearest_work', []))} nearby papers",
                    "",
                ]
            )
    else:
        summary = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        lines.extend(["```json", summary[:12000], "```", ""])
    lines.extend(
        [
            "Approve or redirect with:",
            "",
            "```bash",
            f'openfars decide {payload.get("project_id", "<project>")} {checkpoint} --approve --feedback "..."',
            "```",
        ]
    )
    return "\n".join(lines) + "\n"
