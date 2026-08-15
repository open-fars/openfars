from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .config import MediaConfig
from .models import ModelRouter
from .workspace import Workspace


class MediaProducer:
    """Produces source-linked packages and optionally renders reviewable media binaries."""

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
        outputs: Dict[str, Any] = {"status": "complete"}
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
    ) -> Dict[str, Any]:
        if not self.config.enabled or not self.config.podcast:
            return self._record("podcast", {"status": "disabled", "artifacts": []})
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
        package = "media/podcast/package.json"
        transcript = "media/podcast/transcript.md"
        self.workspace.write_json(package, podcast)
        self.workspace.write_text(transcript, _podcast_markdown(podcast))
        result: Dict[str, Any] = {
            "status": "prepared",
            "package": package,
            "artifacts": [package, transcript],
        }
        if self.config.podcast_render_command:
            rendered = self._render(
                "podcast",
                self.config.podcast_render_command,
                package,
                self.config.podcast_output,
            )
            result.update(rendered)
            result["artifacts"].append("media/podcast/render.json")
            if rendered.get("output"):
                result["artifacts"].append(rendered["output"])
        return self._record("podcast", result)

    def run_video(
        self,
        paper: str,
        result: Mapping[str, Any],
        ledger: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        if not self.config.enabled or not self.config.video:
            return self._record("video", {"status": "disabled", "artifacts": []})
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
        storyboard = "media/video/storyboard.json"
        self.workspace.write_json(storyboard, video)
        result: Dict[str, Any] = {
            "status": "prepared",
            "package": storyboard,
            "artifacts": [storyboard],
        }
        if self.config.video_render_command:
            rendered = self._render(
                "video",
                self.config.video_render_command,
                storyboard,
                self.config.video_output,
            )
            result.update(rendered)
            result["artifacts"].append("media/video/render.json")
            if rendered.get("output"):
                result["artifacts"].append(rendered["output"])
        return self._record("video", result)

    def _render(
        self,
        kind: str,
        command: Sequence[str],
        package: str,
        output: str,
    ) -> Dict[str, Any]:
        package_path = self.workspace.path(package)
        output_path = self.workspace.path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        replacements = {
            "{workspace}": str(self.workspace.project_dir),
            "{package}": str(package_path),
            "{output}": str(output_path),
        }
        argv: List[str] = []
        for argument in command:
            expanded = str(argument)
            for marker, value in replacements.items():
                expanded = expanded.replace(marker, value)
            argv.append(expanded)
        receipt: Dict[str, Any] = {
            "schema": "openfars.media-render/v1",
            "kind": kind,
            "command_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(),
            "executable": Path(argv[0]).name if argv else "",
            "package": package,
            "requested_output": output,
        }
        try:
            completed = subprocess.run(
                argv,
                cwd=self.workspace.project_dir,
                text=True,
                capture_output=True,
                timeout=self.config.render_timeout,
                check=False,
            )
            self.workspace.write_text(f"sessions/media/{kind}.stdout.log", completed.stdout)
            self.workspace.write_text(f"sessions/media/{kind}.stderr.log", completed.stderr)
            receipt["returncode"] = completed.returncode
            if completed.returncode == 0 and output_path.is_file():
                receipt.update(
                    {
                        "status": "rendered",
                        "output": output,
                        "output_sha256": _sha256(output_path),
                        "bytes": output_path.stat().st_size,
                    }
                )
            else:
                receipt.update(
                    {
                        "status": "render_failed",
                        "error": (
                            "renderer returned a non-zero status"
                            if completed.returncode
                            else "renderer did not create the requested output"
                        ),
                    }
                )
        except subprocess.TimeoutExpired:
            receipt.update({"status": "render_failed", "error": "renderer timed out"})
        except OSError:
            receipt.update(
                {"status": "render_failed", "error": "renderer process could not start"}
            )
        self.workspace.write_json(f"media/{kind}/render.json", receipt)
        return {
            "status": receipt["status"],
            "output": receipt.get("output"),
            "render_receipt": f"media/{kind}/render.json",
        }

    def _record(self, kind: str, result: Dict[str, Any]) -> Dict[str, Any]:
        manifest = self.workspace.read_json("media/manifest.json", {})
        manifest[kind] = result
        self.workspace.write_json("media/manifest.json", manifest)
        return result


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
