from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import requests

from .config import ReleaseConfig
from .models import ModelRouter
from .workspace import Workspace


class PublicationError(RuntimeError):
    pass


class ReleaseBuilder:
    """Build a FAIR-ish, reviewable research object before any external write."""

    SAFE_ROOTS = ("artifacts", "code", "paper", "visualizations", "media", "reports")
    SECRET_NAMES = {".env", "wandb_config.yml", "credentials.json", "credentials.yaml"}

    def __init__(
        self,
        config: ReleaseConfig,
        router: ModelRouter,
        workspace: Workspace,
    ):
        self.config = config
        self.router = router
        self.workspace = workspace

    def build(self) -> Dict[str, Any]:
        if not self.config.bundle:
            return {"status": "disabled"}
        selected = self.workspace.read_json("artifacts/selected_idea.json", {})
        result = self.workspace.read_json("artifacts/experiment_result.json", {})
        audit = self.workspace.read_json("paper/citation_audit.json", {})
        release_notes = self.router.complete_json(
            "publisher",
            f"""Prepare metadata for a reproducible open-science release.

Selected idea:
{json.dumps(selected, ensure_ascii=False, indent=2)}

Result:
{json.dumps(result, ensure_ascii=False, indent=2)}

Citation audit:
{json.dumps(audit, ensure_ascii=False, indent=2)}

Return only JSON with summary, limitations, release_notes, and
recommended_license_review. Never claim the result is successful unless the result says so.
""",
            response_kind="release",
        )
        package = self.workspace.path("release/package")
        package.mkdir(parents=True, exist_ok=True)
        copied: List[Path] = []
        for root_name in self.SAFE_ROOTS:
            root = self.workspace.path(root_name)
            if not root.exists():
                continue
            for source in root.rglob("*"):
                if not source.is_file() or source.is_symlink() or self._secret_like(source):
                    continue
                relative = source.relative_to(self.workspace.project_dir)
                destination = package / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied.append(destination)

        self._write_cards(package, selected, result, release_notes)
        copied.extend([package / "README.md", package / "DATA_CARD.md", package / "MODEL_CARD.md"])
        checksums = {
            str(path.relative_to(package)): _sha256(path)
            for path in sorted(set(copied))
            if path.exists()
        }
        (package / "checksums.sha256").write_text(
            "\n".join(f"{digest}  {path}" for path, digest in checksums.items()) + "\n",
            encoding="utf-8",
        )
        crate = self._ro_crate(package, selected, checksums)
        (package / "ro-crate-metadata.json").write_text(
            json.dumps(crate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        archive = self.workspace.path(f"release/{self.workspace.project_id}.zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(package.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    bundle.write(path, path.relative_to(package))
        manifest = {
            "status": "ready_for_human_review",
            "package": str(package),
            "archive": str(archive),
            "archive_sha256": _sha256(archive),
            "files": len(checksums) + 2,
            "external_writes": False,
            "release_notes": release_notes,
        }
        self.workspace.write_json("release/manifest.json", manifest)
        return manifest

    @classmethod
    def _secret_like(cls, path: Path) -> bool:
        name = path.name.lower()
        return (
            name in cls.SECRET_NAMES
            or name.startswith("id_rsa")
            or name.startswith("id_ed25519")
            or name.endswith((".pem", ".key"))
        )

    @staticmethod
    def _write_cards(
        package: Path,
        selected: Mapping[str, Any],
        result: Mapping[str, Any],
        notes: Mapping[str, Any],
    ) -> None:
        readme = f"""# {selected.get("title", "OpenFARS research artifact")}

{notes.get("summary", "")}

## Reproduce

Inspect `artifacts/plan.json`, install the environment recorded with the code, and run
the experiment entry point in `code/`. Verify files with `checksums.sha256`.

## Result status

`{result.get("status", "unknown")}` — {result.get("summary", "")}

## Limitations

{chr(10).join("- " + str(item) for item in notes.get("limitations", []))}

AI assistance and the OpenFARS event trail must be disclosed in downstream publications.
License selection still requires the human owner's review.
"""
        (package / "README.md").write_text(readme, encoding="utf-8")
        (package / "DATA_CARD.md").write_text(
            "# Data card\n\nNo dataset may be redistributed unless its source license and consent permit it.\n"
            "List generated and derived data, provenance, transformations, and exclusions here.\n",
            encoding="utf-8",
        )
        (package / "MODEL_CARD.md").write_text(
            "# Model card\n\nNo checkpoint may be redistributed until base-model licensing, training data,\n"
            "evaluation scope, risks, and intended use have been reviewed.\n",
            encoding="utf-8",
        )

    def _ro_crate(
        self,
        package: Path,
        selected: Mapping[str, Any],
        checksums: Mapping[str, str],
    ) -> Dict[str, Any]:
        graph: List[Dict[str, Any]] = [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": selected.get("title", self.workspace.project_id),
                "description": selected.get("hypothesis", ""),
                "hasPart": [{"@id": path} for path in checksums],
            },
        ]
        for relative, digest in checksums.items():
            graph.append(
                {
                    "@id": relative,
                    "@type": "File",
                    "sha256": digest,
                    "encodingFormat": mimetypes.guess_type(relative)[0]
                    or "application/octet-stream",
                }
            )
        return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


class Publisher:
    """Explicitly authorized external publication adapters."""

    def __init__(self, config: ReleaseConfig, workspace: Workspace):
        self.config = config
        self.workspace = workspace

    def publish(
        self,
        *,
        confirm: bool,
        github: bool = False,
        huggingface_repo: Optional[str] = None,
        modelscope_repo: Optional[str] = None,
        repo_type: str = "dataset",
    ) -> Dict[str, Any]:
        if not confirm:
            raise PublicationError("Publication requires explicit confirm=True")
        manifest = self.workspace.read_json("release/manifest.json")
        if not manifest:
            raise PublicationError("Build and review the release bundle before publishing")
        results: Dict[str, Any] = {}
        if github:
            results["github"] = self._publish_github(Path(manifest["archive"]))
        if huggingface_repo:
            results["huggingface"] = self._publish_huggingface(huggingface_repo, repo_type)
        if modelscope_repo:
            results["modelscope"] = self._publish_modelscope(modelscope_repo, repo_type)
        self.workspace.write_json("release/publication_receipts.json", results)
        return results

    def _publish_github(self, archive: Path) -> Dict[str, Any]:
        token = os.getenv(self.config.github_token_env)
        if not token:
            raise PublicationError(f"Missing {self.config.github_token_env}")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        identity = requests.get("https://api.github.com/user", headers=headers, timeout=30)
        identity.raise_for_status()
        login = identity.json().get("login")
        if login != self.config.github_account:
            raise PublicationError(
                f"Authenticated GitHub account '{login}' is not allowed; expected "
                f"'{self.config.github_account}'"
            )
        release = requests.post(
            f"https://api.github.com/repos/{self.config.github_owner}/"
            f"{self.config.github_repository}/releases",
            headers=headers,
            json={
                "tag_name": f"research-{self.workspace.project_id}",
                "target_commitish": "main",
                "name": f"Research artifact: {self.workspace.project_id}",
                "body": "OpenFARS reproducible research bundle. Review limitations before reuse.",
                "draft": False,
                "prerelease": True,
            },
            timeout=30,
        )
        release.raise_for_status()
        release_data = release.json()
        upload = requests.post(
            f"https://uploads.github.com/repos/{self.config.github_owner}/"
            f"{self.config.github_repository}/releases/{release_data['id']}/assets",
            headers={**headers, "Content-Type": "application/zip"},
            params={"name": archive.name},
            data=archive.read_bytes(),
            timeout=300,
        )
        upload.raise_for_status()
        return {"account": login, "url": release_data.get("html_url")}

    def _publish_huggingface(self, repo_id: str, repo_type: str) -> Dict[str, Any]:
        token = os.getenv(self.config.huggingface_token_env)
        if not token:
            raise PublicationError(f"Missing {self.config.huggingface_token_env}")
        try:
            from huggingface_hub import HfApi
        except ImportError as error:
            raise PublicationError("Install the 'publish' extra for Hugging Face") from error
        api = HfApi(token=token)
        identity = api.whoami()
        namespace = repo_id.split("/", 1)[0] if "/" in repo_id else identity["name"]
        allowed = self.config.huggingface_namespace or identity["name"]
        if namespace != allowed:
            raise PublicationError(
                f"Hugging Face namespace '{namespace}' is not allowed; expected '{allowed}'"
            )
        api.create_repo(repo_id, repo_type=repo_type, private=False, exist_ok=True)
        api.upload_folder(
            repo_id=repo_id,
            repo_type=repo_type,
            folder_path=str(self.workspace.path("release/package")),
            commit_message=f"Publish OpenFARS project {self.workspace.project_id}",
        )
        return {"account": identity["name"], "repo_id": repo_id, "repo_type": repo_type}

    def _publish_modelscope(self, repo_id: str, repo_type: str) -> Dict[str, Any]:
        token = os.getenv("MODELSCOPE_API_TOKEN")
        if not token:
            raise PublicationError("Missing MODELSCOPE_API_TOKEN")
        try:
            from modelscope_hub import HubApi
        except ImportError as error:
            raise PublicationError("Install the 'publish' extra for ModelScope") from error
        api = HubApi(token=token)
        identity = api.whoami()
        username = getattr(identity, "username", str(identity))
        namespace = repo_id.split("/", 1)[0] if "/" in repo_id else username
        if namespace != username:
            raise PublicationError(
                f"ModelScope namespace '{namespace}' does not match authenticated '{username}'"
            )
        if not api.repo_exists(repo_id, repo_type):
            api.create_repo(repo_id, repo_type, visibility="public")
        api.upload_folder(
            repo_id,
            repo_type,
            str(self.workspace.path("release/package")),
            commit_message=f"Publish OpenFARS project {self.workspace.project_id}",
        )
        return {"account": username, "repo_id": repo_id, "repo_type": repo_type}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
