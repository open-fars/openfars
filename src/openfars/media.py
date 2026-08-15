from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Sequence

from .config import MediaConfig
from .models import ModelRouter
from .workspace import Workspace


class MediaProducer:
    """Produces source-linked packages; renderers can turn them into audio/video."""

    def __init__(self, config: MediaConfig, router: ModelRouter, workspace: Workspace):
        self.config = config
        self.router = router
        self.workspace = workspace

    def run(
        self,
        paper: str,
        result: Mapping[str, Any],
        ledger: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        if not self.config.enabled:
            return {"status": "disabled"}
        outputs: Dict[str, Any] = {"status": "prepared"}
        if self.config.podcast:
            outputs["podcast"] = self.run_podcast(paper, result, ledger)
        if self.config.video:
            outputs["video"] = self.run_video(paper, result, ledger)
        self.workspace.write_json("media/manifest.json", outputs)
        return outputs

    def _shared_prompt(
        self,
        paper: str,
        result: Mapping[str, Any],
        ledger: Sequence[Mapping[str, Any]],
    ) -> str:
        return f"""Paper:
{paper}

Observed experiment result:
{json.dumps(result, ensure_ascii=False, indent=2)}

Verified evidence IDs:
{json.dumps(list(ledger), ensure_ascii=False, indent=2)}
"""

    def run_podcast(
        self,
        paper: str,
        result: Mapping[str, Any],
        ledger: Sequence[Mapping[str, Any]],
    ) -> str:
        if not self.config.enabled or not self.config.podcast:
            return "disabled"
        podcast = self.router.complete_json(
            "podcaster",
            self._shared_prompt(paper, result, ledger)
            + """
Create a conversational podcast package. Return only JSON with title, disclosure,
speakers, turns (speaker, text, evidence_refs), show_notes, and pronunciation_notes.
Every factual claim needs a paper evidence ID or must be labeled as project observation.
Do not clone or imitate a real person's voice.
""",
            response_kind="podcast",
        )
        self.workspace.write_json("media/podcast/package.json", podcast)
        self.workspace.write_text("media/podcast/transcript.md", _podcast_markdown(podcast))
        return "media/podcast/package.json"

    def run_video(
        self,
        paper: str,
        result: Mapping[str, Any],
        ledger: Sequence[Mapping[str, Any]],
    ) -> str:
        if not self.config.enabled or not self.config.video:
            return "disabled"
        video = self.router.complete_json(
            "video_producer",
            self._shared_prompt(paper, result, ledger)
            + """
Create a short research video storyboard. Return only JSON with title, format,
disclosure, and scenes (duration_seconds, narration, visual, evidence_refs,
on_screen_text). Use programmatic charts and diagrams; do not fabricate lab footage.
""",
            response_kind="video",
        )
        self.workspace.write_json("media/video/storyboard.json", video)
        return "media/video/storyboard.json"


def _podcast_markdown(package: Mapping[str, Any]) -> str:
    lines = [
        f"# {package.get('title', 'Research podcast')}",
        "",
        str(package.get("disclosure", "")),
        "",
    ]
    for turn in package.get("turns", []):
        refs = " ".join(f"[{value}]" for value in turn.get("evidence_refs", []))
        lines.append(
            f"**{turn.get('speaker', 'Speaker')}:** {turn.get('text', '')} {refs}".rstrip()
        )
        lines.append("")
    return "\n".join(lines)
