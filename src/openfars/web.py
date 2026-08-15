from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .config import OpenFARSConfig
from .human import HumanDecisionRequired, write_decision
from .leaderboards import LeaderboardSubscriber
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
WEB_STATIC_FILES = {
    "office3d.js": "text/javascript; charset=utf-8",
    "three.legacy.module.min.js": "text/javascript; charset=utf-8",
}

AGENT_PROFILES: Dict[str, Dict[str, str]] = {
    "director": {
        "label": "Director",
        "department": "Research Strategy",
        "mission": "Sets the research charter and keeps the team focused on the highest-value question.",
    },
    "librarian": {
        "label": "Librarian",
        "department": "Research Strategy",
        "mission": "Builds the evidence map, finds nearby work, and separates facts from inference.",
    },
    "explorer": {
        "label": "Explorer",
        "department": "Research Strategy",
        "mission": "Searches for genuinely different, falsifiable ideas instead of fluent variations.",
    },
    "critic": {
        "label": "Critic",
        "department": "Research Strategy",
        "mission": "Attacks novelty, confounders, measurements, and the weakest assumptions.",
    },
    "task_designer": {
        "label": "Task Designer",
        "department": "Experiment Design",
        "mission": "Turns an approved idea into a precise research task with an executable decision rule.",
    },
    "planner": {
        "label": "Planner",
        "department": "Experiment Design",
        "mission": "Designs the cheapest decisive experiment, controls, seeds, and stop conditions.",
    },
    "experimenter": {
        "label": "Experimenter",
        "department": "Experiment Design",
        "mission": "Implements, runs, debugs, and preserves reproducible experimental evidence.",
    },
    "evaluator": {
        "label": "Evaluator",
        "department": "Experiment Design",
        "mission": "Applies the decision rule and decides whether to iterate, advance, or stop.",
    },
    "visualizer": {
        "label": "Visualizer",
        "department": "Research Media",
        "mission": "Turns measured results into data-linked figures without visual overclaiming.",
    },
    "writer": {
        "label": "Writer",
        "department": "Research Media",
        "mission": "Writes the paper from the evidence ledger and keeps every claim traceable.",
    },
    "podcaster": {
        "label": "Podcaster",
        "department": "Research Media",
        "mission": "Turns verified claims into an engaging, clearly disclosed research conversation.",
    },
    "video_producer": {
        "label": "Video Producer",
        "department": "Research Media",
        "mission": "Builds a source-linked visual story without fabricating experimental footage.",
    },
    "publisher": {
        "label": "Publisher",
        "department": "Open Science",
        "mission": "Packages reproducible code, data, metadata, and release checks for human approval.",
    },
}

ACTIVE_AGENT_BY_STAGE = {
    "created": "director",
    "direction_ready": "librarian",
    "literature_ready": "explorer",
    "revising_ideas": "explorer",
    "ideas_ready": "critic",
    "idea_approved": "task_designer",
    "task_ready": "planner",
    "experimenting": "experimenter",
    "results_approved": "visualizer",
    "visualization_ready": "writer",
    "paper_ready": "podcaster",
    "podcast_ready": "video_producer",
    "media_ready": "publisher",
}


class WebControlPlane:
    """Domain API projected from durable files; browser state is never authoritative."""

    def __init__(self, config: OpenFARSConfig):
        self.config = config
        self._threads: Dict[str, threading.Thread] = {}
        self._chat_locks: Dict[tuple[str, str], threading.Lock] = {}
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

    def model_registry(self) -> Dict[str, Any]:
        snapshot = LeaderboardSubscriber(self.config).status()
        return {
            "policy": "advisory_only_no_silent_route_changes",
            "routes": [
                {
                    "name": route.name,
                    "backend": route.backend,
                    "model": route.model,
                }
                for route in self.config.models.values()
            ],
            "assignments": [
                {
                    "agent": name,
                    "label": profile["label"],
                    "models": [
                        {
                            "route": route_name,
                            "backend": self.config.models[route_name].backend,
                            "model": self.config.models[route_name].model,
                        }
                        for route_name in self.config.agent(name).routes()
                    ],
                }
                for name, profile in AGENT_PROFILES.items()
                if name in self.config.agents
            ],
            "refreshed_at": snapshot.get("refreshed_at"),
            "sources": [
                {"name": item.get("name"), "status": item.get("status")}
                for item in snapshot.get("sources", [])
            ],
        }

    def agent_roster(self, project_id: str) -> List[Dict[str, Any]]:
        workspace = self._workspace(project_id, must_exist=True)
        state = workspace.read_json("state.json", {})
        manifest = workspace.read_json("manifest.json", {})
        handoffs = self._read_handoffs(workspace)
        events = self.events(project_id, 0)["events"]
        running = self.is_running(project_id)
        active = ACTIVE_AGENT_BY_STAGE.get(str(state.get("stage", "")))
        lifecycle: Dict[str, Dict[str, Any]] = {}
        for event in events:
            if event.get("type") != "agent.lifecycle":
                continue
            data = event.get("data", {})
            name = data.get("agent") if isinstance(data, Mapping) else None
            if name in AGENT_PROFILES:
                lifecycle[str(name)] = {
                    "phase": data.get("phase"),
                    "error": data.get("error"),
                    "time": event.get("time"),
                }

        rows = []
        for index, (name, profile) in enumerate(AGENT_PROFILES.items(), start=1):
            own_handoffs = [item for item in handoffs if item.get("agent") == name]
            latest = own_handoffs[-1] if own_handoffs else None
            last_lifecycle = lifecycle.get(name, {})
            phase = last_lifecycle.get("phase")
            if phase == "error":
                status = "error"
            elif running and (phase == "start" or name == active):
                status = "working"
            elif own_handoffs:
                status = "done"
            elif state.get("stage") == "rejected":
                status = "stopped"
            elif name == active:
                status = "ready"
            else:
                status = "queued"

            configured = ((manifest.get("agents") or {}).get(name) or {}).get("models", [])
            if not configured:
                configured = [
                    {
                        "route": route_name,
                        "backend": self.config.models[route_name].backend,
                        "model": self.config.models[route_name].model,
                    }
                    for route_name in self.config.agent(name).routes()
                ]
            rows.append(
                {
                    "name": name,
                    "number": index,
                    **profile,
                    "status": status,
                    "runs": len(own_handoffs),
                    "models": configured,
                    "summary": (
                        latest.get("summary", "")
                        if latest
                        else self._pending_agent_summary(name, status)
                    ),
                    "last_activity": ((latest or {}).get("time") or last_lifecycle.get("time")),
                    "artifacts": (latest or {}).get("artifacts", []),
                    "open_questions": (latest or {}).get("open_questions", []),
                    "latest_handoff": latest,
                }
            )
        return rows

    def agent(self, project_id: str, agent_name: str) -> Dict[str, Any]:
        self._validate_agent(agent_name)
        workspace = self._workspace(project_id, must_exist=True)
        roster = {item["name"]: item for item in self.agent_roster(project_id)}
        handoffs = [
            item for item in self._read_handoffs(workspace) if item.get("agent") == agent_name
        ]
        events = [
            event
            for event in self.events(project_id, 0)["events"]
            if isinstance(event.get("data"), Mapping) and event["data"].get("agent") == agent_name
        ]
        artifacts: Dict[str, Dict[str, Any]] = {}
        for handoff in handoffs:
            for artifact in handoff.get("artifacts", []):
                if isinstance(artifact, Mapping) and artifact.get("path"):
                    artifacts[str(artifact["path"])] = dict(artifact)
        return {
            **roster[agent_name],
            "handoffs": handoffs,
            "artifacts": list(artifacts.values()),
            "recent_events": events[-12:],
            "chat": self._agent_chat(workspace, agent_name),
        }

    def ask_agent(self, project_id: str, agent_name: str, question: str) -> Dict[str, Any]:
        self._validate_agent(agent_name)
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        if len(question) > 4000:
            raise ValueError("question must be at most 4000 characters")
        workspace = self._workspace(project_id, must_exist=True)
        chat_lock = self._chat_lock(project_id, agent_name)
        with chat_lock:
            snapshot = self.agent(project_id, agent_name)
            history = snapshot.get("chat", [])[-8:]
            fallback = self._evidence_status_answer(snapshot)
            answer = fallback
            source = "evidence_summary"
            model_name = None
            route_agent = self._safe_status_route(agent_name)
            if route_agent is not None:
                route = self.config.model_for_agent(route_agent)
                model_name = route.model
                if route.backend != "mock":
                    prompt = self._agent_status_prompt(workspace, snapshot, question, history)
                    router = ModelRouter(self.config, workspace)
                    try:
                        answer = router.complete(
                            route_agent,
                            prompt,
                            response_kind="agent_status",
                            context={"session_id": (f"{project_id}-{agent_name}-web-status")},
                        ).strip()
                        source = "model"
                    except RuntimeError as error:
                        workspace.append_event(
                            "web.agent_chat_fallback",
                            {
                                "agent": agent_name,
                                "error_type": type(error).__name__,
                            },
                        )
                    finally:
                        router.close()

            now = datetime.now(timezone.utc).isoformat()
            records = [
                {"role": "user", "content": question, "time": now},
                {
                    "role": "agent",
                    "content": answer,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "source": source,
                    "model": model_name if source == "model" else None,
                },
            ]
            chat = [*self._agent_chat(workspace, agent_name), *records][-80:]
            workspace.write_json(f"sessions/web_agent_chats/{agent_name}.json", chat)
            workspace.append_event(
                "web.agent_asked",
                {
                    "agent": agent_name,
                    "source": source,
                    "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
                    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                },
            )
            return {"agent": agent_name, "message": records[-1], "chat": chat}

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
        handoffs = self._read_handoffs(workspace)
        return {
            "project_id": project_id,
            "state": state,
            "manifest": workspace.read_json("manifest.json", {}),
            "running": self.is_running(project_id),
            "pending_decisions": pending,
            "handoffs": handoffs,
            "agents": self.agent_roster(project_id),
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

    @staticmethod
    def _read_handoffs(workspace: Workspace) -> List[Dict[str, Any]]:
        handoffs = []
        for path in sorted(workspace.path("handoffs").glob("*.json")):
            try:
                handoffs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return handoffs

    @staticmethod
    def _pending_agent_summary(agent_name: str, status: str) -> str:
        if status == "working":
            return "Working now. Open the desk for the latest activity."
        if status == "ready":
            return "Ready to start when the current workflow resumes."
        if status == "stopped":
            return "The research run stopped before this desk received a handoff."
        if status == "error":
            return "This desk hit an error. Open it to inspect the latest event."
        return f"Waiting for upstream context before {agent_name} can begin."

    @staticmethod
    def _agent_chat(workspace: Workspace, agent_name: str) -> List[Dict[str, Any]]:
        chat = workspace.read_json(f"sessions/web_agent_chats/{agent_name}.json", [])
        return [dict(item) for item in chat if isinstance(item, Mapping)]

    def _chat_lock(self, project_id: str, agent_name: str) -> threading.Lock:
        key = (project_id, agent_name)
        with self._lock:
            return self._chat_locks.setdefault(key, threading.Lock())

    def _validate_agent(self, agent_name: str) -> None:
        if agent_name not in AGENT_PROFILES or agent_name not in self.config.agents:
            raise ValueError(f"Unknown office agent '{agent_name}'")

    def _safe_status_route(self, agent_name: str) -> Optional[str]:
        candidates = [agent_name, "director", "evaluator", "writer"]
        for candidate in dict.fromkeys(candidates):
            if candidate not in self.config.agents:
                continue
            route = self.config.model_for_agent(candidate)
            if route.backend != "deepseek-harness":
                return candidate
        return None

    @staticmethod
    def _evidence_status_answer(snapshot: Mapping[str, Any]) -> str:
        label = str(snapshot.get("label", snapshot.get("name", "Agent")))
        status = str(snapshot.get("status", "queued"))
        summary = str(snapshot.get("summary", "No handoff has been recorded yet."))
        artifact_names = [
            str(item.get("path"))
            for item in snapshot.get("artifacts", [])
            if isinstance(item, Mapping) and item.get("path")
        ]
        questions = [str(item) for item in snapshot.get("open_questions", []) if item]
        parts = [f"{label} status: {status}.", summary]
        if artifact_names:
            parts.append("Outputs: " + ", ".join(artifact_names[:5]) + ".")
        if questions:
            parts.append("Open questions: " + "; ".join(questions[:4]) + ".")
        return " ".join(parts)

    def _agent_status_prompt(
        self,
        workspace: Workspace,
        snapshot: Mapping[str, Any],
        question: str,
        history: List[Dict[str, Any]],
    ) -> str:
        excerpts: Dict[str, str] = {}
        remaining = 8000
        for artifact in list(snapshot.get("artifacts", []))[-5:]:
            if remaining <= 0 or not isinstance(artifact, Mapping):
                break
            relative = str(artifact.get("path", ""))
            parts = Path(relative).parts
            if not parts or parts[0] not in VISIBLE_ROOTS:
                continue
            path = workspace.path(relative)
            if not path.is_file() or path.suffix.lower() not in {
                ".json",
                ".md",
                ".txt",
                ".yaml",
                ".yml",
            }:
                continue
            content = workspace.read_text(relative)
            excerpt = content[: min(remaining, 2400)]
            excerpts[relative] = excerpt
            remaining -= len(excerpt)

        state = workspace.read_json("state.json", {})
        context = {
            "project": {
                "project_id": workspace.project_id,
                "topics": state.get("topics", []),
                "stage": state.get("stage"),
            },
            "agent": {
                key: snapshot.get(key)
                for key in (
                    "name",
                    "label",
                    "mission",
                    "status",
                    "summary",
                    "models",
                    "handoffs",
                    "open_questions",
                )
            },
            "artifact_excerpts": excerpts,
            "recent_chat": history,
        }
        return (
            "This is a read-only status conversation inside the OpenFARS WebUI. "
            f"Answer as the {snapshot.get('label', snapshot.get('name'))} role. "
            "Use only the recorded context below. Clearly distinguish completed work, "
            "current work, blockers, and the next step. If the evidence does not answer "
            "the question, say so. Do not claim to run tools, change files, or complete work "
            "during this conversation. Keep the answer concise and concrete.\n\n"
            f"RECORDED CONTEXT\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"USER QUESTION\n{question}"
        )

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
            if len(parts) == 2 and parts[0] == "static" and parts[1] in WEB_STATIC_FILES:
                content = files("openfars").joinpath(f"web/{parts[1]}").read_bytes()
                etag = f'"{hashlib.sha256(content).hexdigest()}"'
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.send_header("ETag", etag)
                    self._security_headers(cache_control="public, max-age=3600")
                    self.end_headers()
                    return
                self._bytes(
                    content,
                    WEB_STATIC_FILES[parts[1]],
                    cache_control="public, max-age=3600",
                    etag=etag,
                )
                return
            if parts == ["api", "health"]:
                self._json({"status": "ok"})
                return
            if parts == ["api", "projects"]:
                self._json({"projects": self.control.list_projects()})
                return
            if parts == ["api", "models"]:
                self._json(self.control.model_registry())
                return
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self._json(self.control.project(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "agents":
                self._json(self.control.agent(parts[2], parts[4]))
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
            if (
                len(parts) == 6
                and parts[:2] == ["api", "projects"]
                and parts[3] == "agents"
                and parts[5] == "ask"
            ):
                self._json(
                    self.control.ask_agent(parts[2], parts[4], str(payload.get("question", "")))
                )
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

    def _bytes(
        self,
        data: bytes,
        content_type: str,
        *,
        status: int = 200,
        cache_control: str = "no-store",
        etag: Optional[str] = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if etag:
            self.send_header("ETag", etag)
        self._security_headers(cache_control=cache_control)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _security_headers(self, *, cache_control: str = "no-store") -> None:
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
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
    _refresh_leaderboards_async(config)
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


def _refresh_leaderboards_async(config: OpenFARSConfig) -> Optional[threading.Thread]:
    if not config.leaderboards.enabled:
        return None

    def refresh() -> None:
        try:
            LeaderboardSubscriber(config).refresh()
        except Exception:
            # The control plane remains usable offline; the snapshot exposes feed failures.
            return

    thread = threading.Thread(target=refresh, name="openfars-model-registry", daemon=True)
    thread.start()
    return thread


def _secret_like(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SECRET_NAMES
        or name.startswith(("id_rsa", "id_ed25519"))
        or name.endswith((".pem", ".key"))
    )
