from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .config import OpenFARSConfig
from .human import HumanDecisionRequired, write_decision
from .models import ModelRouter
from .orchestrator import ResearchOrchestrator
from .release import ReleaseBuilder
from .workspace import Workspace

PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VISIBLE_ROOTS = {
    "artifacts",
    "paper",
    "visualizations",
    "media",
    "reports",
    "release",
    "handoffs",
    "decisions",
}
SECRET_NAMES = {".env", "wandb_config.yml", "credentials.json", "credentials.yaml"}


class WebControlPlane:
    """Domain API projected from durable files; browser state is never authoritative."""

    def __init__(self, config: OpenFARSConfig):
        self.config = config
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def list_projects(self) -> List[Dict[str, Any]]:
        root = self.config.runtime.output_dir
        if not root.exists():
            return []
        projects = []
        for path in root.iterdir():
            if not path.is_dir() or path.name.startswith("_"):
                continue
            state_path = path / "state.json"
            if not state_path.is_file():
                continue
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            projects.append(
                {
                    "project_id": path.name,
                    "stage": state.get("stage", "unknown"),
                    "topics": state.get("topics", []),
                    "running": self.is_running(path.name),
                    "updated_at": state_path.stat().st_mtime,
                }
            )
        return sorted(projects, key=lambda item: item["updated_at"], reverse=True)

    def project(self, project_id: str) -> Dict[str, Any]:
        workspace = self._workspace(project_id, must_exist=True)
        state = workspace.read_json("state.json", {})
        pending = []
        for request in workspace.path("decisions").glob("*.request.json"):
            checkpoint = request.name.split(".", 1)[0]
            if not workspace.path(f"decisions/{checkpoint}.decision.json").exists():
                pending.append(
                    {
                        "checkpoint": checkpoint,
                        "request": workspace.read_json(f"decisions/{checkpoint}.request.json", {}),
                        "packet": workspace.read_text(f"decisions/{checkpoint}.packet.md"),
                    }
                )
        handoffs = []
        for path in sorted(workspace.path("handoffs").glob("*.json")):
            try:
                handoffs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return {
            "project_id": project_id,
            "state": state,
            "manifest": workspace.read_json("manifest.json", {}),
            "running": self.is_running(project_id),
            "pending_decisions": pending,
            "handoffs": handoffs,
            "artifacts": self.artifacts(project_id),
            "events": self.events(project_id, max(0, self.event_count(project_id) - 120)),
        }

    def event_count(self, project_id: str) -> int:
        workspace = self._workspace(project_id, must_exist=True)
        path = workspace.path("events.jsonl")
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def events(self, project_id: str, after: int = 0) -> Dict[str, Any]:
        workspace = self._workspace(project_id, must_exist=True)
        path = workspace.path("events.jsonl")
        rows = []
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle):
                    if index < after or not line.strip():
                        continue
                    try:
                        rows.append({"seq": index + 1, **json.loads(line)})
                    except json.JSONDecodeError:
                        continue
        return {"events": rows, "next": after + len(rows)}

    def artifacts(self, project_id: str) -> List[Dict[str, Any]]:
        workspace = self._workspace(project_id, must_exist=True)
        rows = []
        for root in VISIBLE_ROOTS:
            directory = workspace.path(root)
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if not path.is_file() or path.is_symlink() or _secret_like(path):
                    continue
                rows.append(
                    {
                        "path": str(path.relative_to(workspace.project_dir)),
                        "bytes": path.stat().st_size,
                    }
                )
        return sorted(rows, key=lambda item: item["path"])

    def artifact(self, project_id: str, relative: str) -> Path:
        workspace = self._workspace(project_id, must_exist=True)
        path = workspace.path(relative)
        parts = Path(relative).parts
        if not parts or parts[0] not in VISIBLE_ROOTS or _secret_like(path):
            raise PermissionError("Artifact is not browser-visible")
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(relative)
        return path

    def start(self, project_id: str, topics: Optional[List[str]] = None) -> None:
        if not PROJECT_ID.fullmatch(project_id):
            raise ValueError("Invalid project_id")
        with self._lock:
            existing = self._threads.get(project_id)
            if existing and existing.is_alive():
                raise RuntimeError("Project is already running")

            def worker() -> None:
                try:
                    ResearchOrchestrator(self.config).run(topics or [], project_id=project_id)
                except HumanDecisionRequired:
                    return
                except Exception as error:
                    workspace = Workspace(self.config.runtime.output_dir, project_id)
                    workspace.append_event("web.run_failed", {"error": str(error)})

            thread = threading.Thread(target=worker, name=f"openfars-{project_id}", daemon=True)
            self._threads[project_id] = thread
            thread.start()

    def decide(self, project_id: str, checkpoint: str, decision: Mapping[str, Any]) -> None:
        workspace = self._workspace(project_id, must_exist=True)
        write_decision(
            workspace,
            checkpoint,
            action=str(decision.get("action", "")),
            selected_id=decision.get("selected_id"),
            feedback=str(decision.get("feedback", "")),
            overrides=decision.get("overrides") or {},
        )
        self.start(project_id)

    def bundle(self, project_id: str) -> Mapping[str, Any]:
        workspace = self._workspace(project_id, must_exist=True)
        return ReleaseBuilder(
            self.config.release, ModelRouter(self.config, workspace), workspace
        ).build()

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(project_id)
            return bool(thread and thread.is_alive())

    def _workspace(self, project_id: str, *, must_exist: bool) -> Workspace:
        if not PROJECT_ID.fullmatch(project_id):
            raise ValueError("Invalid project_id")
        project = self.config.runtime.output_dir / project_id
        if must_exist and not (project / "state.json").is_file():
            raise FileNotFoundError(project_id)
        return Workspace(self.config.runtime.output_dir, project_id)


class OpenFARSRequestHandler(BaseHTTPRequestHandler):
    server_version = "OpenFARS/0.2"

    @property
    def control(self) -> WebControlPlane:
        return self.server.control  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            parts = [unquote(item) for item in parsed.path.split("/") if item]
            if parsed.path in {"/", "/index.html"}:
                content = files("openfars").joinpath("web/index.html").read_bytes()
                self._bytes(content, "text/html; charset=utf-8")
                return
            if parts == ["api", "health"]:
                self._json({"status": "ok"})
                return
            if parts == ["api", "projects"]:
                self._json({"projects": self.control.list_projects()})
                return
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self._json(self.control.project(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "events":
                after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self._json(self.control.events(parts[2], max(0, after)))
                return
            if (
                len(parts) == 5
                and parts[:2] == ["api", "projects"]
                and parts[3:] == ["events", "stream"]
            ):
                after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self._event_stream(parts[2], max(0, after))
                return
            if len(parts) >= 5 and parts[:2] == ["api", "projects"] and parts[3] == "artifacts":
                relative = "/".join(parts[4:])
                path = self.control.artifact(parts[2], relative)
                self._bytes(
                    path.read_bytes(),
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, PermissionError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
        except BrokenPipeError:
            return

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._require_same_origin_json()
            payload = self._read_json()
            parsed = urlparse(self.path)
            parts = [unquote(item) for item in parsed.path.split("/") if item]
            if parts == ["api", "projects"]:
                project_id = str(payload.get("project_id", ""))
                topics = payload.get("topics", [])
                if not isinstance(topics, list) or not topics:
                    raise ValueError("topics must be a non-empty list")
                self.control.start(project_id, [str(item) for item in topics])
                self._json({"status": "started", "project_id": project_id}, status=202)
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "resume":
                self.control.start(parts[2])
                self._json({"status": "started"}, status=202)
                return
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "decisions":
                self.control.decide(parts[2], parts[4], payload)
                self._json({"status": "recorded_and_resumed"}, status=202)
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "bundle":
                self._json(dict(self.control.bundle(parts[2])))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, RuntimeError, PermissionError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))

    def _event_stream(self, project_id: str, after: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._security_headers()
        self.end_headers()
        deadline = time.monotonic() + 30
        cursor = after
        while time.monotonic() < deadline:
            page = self.control.events(project_id, cursor)
            for event in page["events"]:
                self.wfile.write(
                    f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                )
                cursor = int(event["seq"])
            self.wfile.write(b": keepalive\n\n")
            self.wfile.flush()
            time.sleep(self.control.config.web.event_poll_ms / 1000)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("JSON body must be between 1 byte and 1 MiB")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _require_same_origin_json(self) -> None:
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise PermissionError("Content-Type must be application/json")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            raise PermissionError("Cross-origin write refused")

    def _json(self, data: Mapping[str, Any], *, status: int = 200) -> None:
        self._bytes(
            (json.dumps(data, ensure_ascii=False) + "\n").encode(),
            "application/json; charset=utf-8",
            status=status,
        )

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status=status)

    def _bytes(self, data: bytes, content_type: str, *, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class OpenFARSWebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, config: OpenFARSConfig):
        super().__init__((config.web.host, config.web.port), OpenFARSRequestHandler)
        self.control = WebControlPlane(config)


def serve(config: OpenFARSConfig, *, open_browser: Optional[bool] = None) -> None:
    server = OpenFARSWebServer(config)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}"
    print(f"OpenFARS WebUI: {url}")
    should_open = config.web.open_browser if open_browser is None else open_browser
    if should_open:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


def _secret_like(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SECRET_NAMES
        or name.startswith(("id_rsa", "id_ed25519"))
        or name.endswith((".pem", ".key"))
    )
