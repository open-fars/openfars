from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional

import yaml


@dataclass(frozen=True)
class ModelRoute:
    """One named route to a model or an agent harness."""

    name: str
    model: str
    backend: str = "litellm"
    temperature: Optional[float] = 0.2
    max_tokens: int = 4096
    api_key_env: Optional[str] = None
    api_base: Optional[str] = None
    api_base_env: Optional[str] = None
    provider: str = "deepseek-official"
    timeout: int = 300
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, raw: Mapping[str, Any]) -> "ModelRoute":
        known = {
            "model",
            "backend",
            "temperature",
            "max_tokens",
            "api_key_env",
            "api_base",
            "api_base_env",
            "provider",
            "timeout",
        }
        if "model" not in raw:
            raise ValueError(f"Model route '{name}' is missing 'model'")
        return cls(
            name=name,
            model=str(raw["model"]),
            backend=str(raw.get("backend", "litellm")),
            temperature=(
                None if raw.get("temperature", 0.2) is None else float(raw.get("temperature", 0.2))
            ),
            max_tokens=int(raw.get("max_tokens", 4096)),
            api_key_env=raw.get("api_key_env"),
            api_base=raw.get("api_base"),
            api_base_env=raw.get("api_base_env"),
            provider=str(raw.get("provider", "deepseek-official")),
            timeout=int(raw.get("timeout", 300)),
            extra={key: value for key, value in raw.items() if key not in known},
        )

    def resolved_api_base(self) -> Optional[str]:
        if self.api_base_env:
            return os.getenv(self.api_base_env) or self.api_base
        return self.api_base


@dataclass(frozen=True)
class AgentRoute:
    name: str
    model: str
    model_pool: List[str] = field(default_factory=list)
    system_prompt: str = ""
    context_budget_chars: int = 60000

    def routes(self) -> List[str]:
        """Ordered model portfolio; the primary route is always first."""
        return list(dict.fromkeys([self.model, *self.model_pool]))


@dataclass(frozen=True)
class SearchConfig:
    candidates: int = 8
    finalists: int = 3
    concurrency: int = 4
    judges: List[str] = field(default_factory=lambda: ["critic", "reviewer"])
    operators: List[str] = field(
        default_factory=lambda: [
            "inversion",
            "cross-domain transfer",
            "bottleneck removal",
            "scaling-law break",
            "measurement attack",
            "mechanism-first",
        ]
    )
    weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "novelty": 0.25,
            "impact": 0.2,
            "feasibility": 0.15,
            "falsifiability": 0.25,
            "evidence": 0.15,
        }
    )


@dataclass(frozen=True)
class HumanConfig:
    mode: str = "off"
    checkpoints: List[str] = field(default_factory=lambda: ["idea"])
    packet_candidates: int = 3


@dataclass(frozen=True)
class EvidenceConfig:
    enabled: bool = True
    provider: str = "openalex"
    papers_per_query: int = 8
    timeout: int = 15


@dataclass(frozen=True)
class ExecutionConfig:
    enabled: bool = False
    agent: str = "experimenter"
    result_file: str = "experiment_result.json"
    target: Optional[str] = None
    command: Optional[str] = None
    timeout: int = 86400
    max_iterations: int = 3


@dataclass(frozen=True)
class MediaConfig:
    enabled: bool = True
    podcast: bool = True
    video: bool = True
    podcast_render_command: List[str] = field(default_factory=list)
    video_render_command: List[str] = field(default_factory=list)
    podcast_output: str = "media/podcast/podcast.wav"
    video_output: str = "media/video/video.mp4"
    render_timeout: int = 3600


@dataclass(frozen=True)
class LeaderboardConfig:
    enabled: bool = True
    refresh_hours: int = 24
    sources: List[str] = field(
        default_factory=lambda: [
            "artificial-analysis",
            "swe-bench",
            "deepresearch-bench",
            "terminal-bench",
            "paperbench",
            "live-research-bench",
            "artificial-analysis-media",
        ]
    )
    artificial_analysis_key_env: str = "ARTIFICIAL_ANALYSIS_API_KEY"


@dataclass(frozen=True)
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    event_poll_ms: int = 750


@dataclass(frozen=True)
class ReleaseConfig:
    bundle: bool = True
    github_account: str = "Dingrui-Wang"
    github_owner: str = "open-fars"
    github_repository: str = "openfars"
    github_token_env: str = "GITHUB_TOKEN"
    huggingface_token_env: str = "HF_TOKEN"
    huggingface_namespace: Optional[str] = None


@dataclass(frozen=True)
class ComputeTarget:
    name: str
    host: str
    user: str
    port: int = 22
    identity_file: Optional[str] = None
    identity_file_env: Optional[str] = None
    workdir: str = "/tmp/openfars"
    output_dir: str = "/tmp/openfars-output"
    datasets_dir: Optional[str] = None
    models_dir: Optional[str] = None
    strict_host_key_checking: bool = True

    @classmethod
    def from_dict(cls, name: str, raw: Mapping[str, Any]) -> "ComputeTarget":
        if not raw.get("host") or not raw.get("user"):
            raise ValueError(f"Compute target '{name}' requires host and user")
        return cls(
            name=name,
            host=str(raw["host"]),
            user=str(raw["user"]),
            port=int(raw.get("port", 22)),
            identity_file=raw.get("identity_file"),
            identity_file_env=raw.get("identity_file_env"),
            workdir=str(raw.get("workdir", "/tmp/openfars")),
            output_dir=str(raw.get("output_dir", "/tmp/openfars-output")),
            datasets_dir=raw.get("datasets_dir"),
            models_dir=raw.get("models_dir"),
            strict_host_key_checking=bool(raw.get("strict_host_key_checking", True)),
        )

    def resolved_identity_file(self) -> Path:
        value = os.getenv(self.identity_file_env, "") if self.identity_file_env else ""
        value = value or self.identity_file or ""
        if not value:
            raise ValueError(
                f"Compute target '{self.name}' has no SSH identity; set identity_file_env"
            )
        return Path(value).expanduser().resolve()


@dataclass(frozen=True)
class RuntimeConfig:
    output_dir: Path = Path("outputs")
    seed: int = 17


@dataclass(frozen=True)
class OpenFARSConfig:
    models: Mapping[str, ModelRoute]
    agents: Mapping[str, AgentRoute]
    search: SearchConfig = field(default_factory=SearchConfig)
    human: HumanConfig = field(default_factory=HumanConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    leaderboards: LeaderboardConfig = field(default_factory=LeaderboardConfig)
    web: WebConfig = field(default_factory=WebConfig)
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    compute: Mapping[str, ComputeTarget] = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    source_path: Optional[Path] = None

    @classmethod
    def load(cls, path: str | Path) -> "OpenFARSConfig":
        source = Path(path).expanduser().resolve()
        with source.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError("Configuration root must be a mapping")

        models = {
            name: ModelRoute.from_dict(name, value or {})
            for name, value in (raw.get("models") or {}).items()
        }
        agents = {
            name: AgentRoute(
                name=name,
                model=str((value or {}).get("model", "")),
                model_pool=[str(item) for item in (value or {}).get("model_pool", [])],
                system_prompt=str((value or {}).get("system_prompt", "")),
                context_budget_chars=max(
                    4000, int((value or {}).get("context_budget_chars", 60000))
                ),
            )
            for name, value in (raw.get("agents") or {}).items()
        }

        search_raw = raw.get("search") or {}
        default_search = SearchConfig()
        search = SearchConfig(
            candidates=max(1, int(search_raw.get("candidates", default_search.candidates))),
            finalists=max(1, int(search_raw.get("finalists", default_search.finalists))),
            concurrency=max(1, int(search_raw.get("concurrency", default_search.concurrency))),
            judges=list(search_raw.get("judges", default_search.judges)),
            operators=list(search_raw.get("operators", default_search.operators)),
            weights=dict(search_raw.get("weights", default_search.weights)),
        )
        human_raw = raw.get("human") or {}
        human = HumanConfig(
            mode=str(human_raw.get("mode", "off")),
            checkpoints=list(human_raw.get("checkpoints", ["idea"])),
            packet_candidates=max(1, int(human_raw.get("packet_candidates", 3))),
        )
        evidence_raw = raw.get("evidence") or {}
        evidence = EvidenceConfig(
            enabled=bool(evidence_raw.get("enabled", True)),
            provider=str(evidence_raw.get("provider", "openalex")),
            papers_per_query=max(1, int(evidence_raw.get("papers_per_query", 8))),
            timeout=max(1, int(evidence_raw.get("timeout", 15))),
        )
        execution_raw = raw.get("execution") or {}
        execution = ExecutionConfig(
            enabled=bool(execution_raw.get("enabled", False)),
            agent=str(execution_raw.get("agent", "experimenter")),
            result_file=str(execution_raw.get("result_file", "experiment_result.json")),
            target=execution_raw.get("target"),
            command=execution_raw.get("command"),
            timeout=max(1, int(execution_raw.get("timeout", 86400))),
            max_iterations=max(1, int(execution_raw.get("max_iterations", 3))),
        )
        media_raw = raw.get("media") or {}
        media = MediaConfig(
            enabled=bool(media_raw.get("enabled", True)),
            podcast=bool(media_raw.get("podcast", True)),
            video=bool(media_raw.get("video", True)),
            podcast_render_command=_string_list(
                media_raw.get("podcast_render_command", []),
                "media.podcast_render_command",
            ),
            video_render_command=_string_list(
                media_raw.get("video_render_command", []),
                "media.video_render_command",
            ),
            podcast_output=str(
                media_raw.get("podcast_output", "media/podcast/podcast.wav")
            ),
            video_output=str(media_raw.get("video_output", "media/video/video.mp4")),
            render_timeout=max(1, int(media_raw.get("render_timeout", 3600))),
        )
        leaderboard_raw = raw.get("leaderboards") or {}
        default_leaderboards = LeaderboardConfig()
        leaderboards = LeaderboardConfig(
            enabled=bool(leaderboard_raw.get("enabled", True)),
            refresh_hours=max(1, int(leaderboard_raw.get("refresh_hours", 24))),
            sources=list(leaderboard_raw.get("sources", default_leaderboards.sources)),
            artificial_analysis_key_env=str(
                leaderboard_raw.get(
                    "artificial_analysis_key_env",
                    "ARTIFICIAL_ANALYSIS_API_KEY",
                )
            ),
        )
        web_raw = raw.get("web") or {}
        web = WebConfig(
            host=str(web_raw.get("host", "127.0.0.1")),
            port=max(0, min(65535, int(web_raw.get("port", 8765)))),
            open_browser=bool(web_raw.get("open_browser", True)),
            event_poll_ms=max(100, int(web_raw.get("event_poll_ms", 750))),
        )
        release_raw = raw.get("release") or {}
        release = ReleaseConfig(
            bundle=bool(release_raw.get("bundle", True)),
            github_account=str(release_raw.get("github_account", "Dingrui-Wang")),
            github_owner=str(release_raw.get("github_owner", "open-fars")),
            github_repository=str(release_raw.get("github_repository", "openfars")),
            github_token_env=str(release_raw.get("github_token_env", "GITHUB_TOKEN")),
            huggingface_token_env=str(release_raw.get("huggingface_token_env", "HF_TOKEN")),
            huggingface_namespace=release_raw.get("huggingface_namespace"),
        )
        compute = {
            name: ComputeTarget.from_dict(name, value or {})
            for name, value in (raw.get("compute") or {}).get("targets", {}).items()
        }
        runtime_raw = raw.get("runtime") or {}
        output_dir = Path(runtime_raw.get("output_dir", "outputs")).expanduser()
        if not output_dir.is_absolute():
            output_dir = (source.parent / output_dir).resolve()
        runtime = RuntimeConfig(
            output_dir=output_dir,
            seed=int(runtime_raw.get("seed", 17)),
        )
        config = cls(
            models=models,
            agents=agents,
            search=search,
            human=human,
            evidence=evidence,
            execution=execution,
            media=media,
            leaderboards=leaderboards,
            web=web,
            release=release,
            compute=compute,
            runtime=runtime,
            source_path=source,
        )
        config.validate()
        return config

    def validate(self) -> None:
        required = {
            "director",
            "librarian",
            "explorer",
            "critic",
            "reviewer",
            "task_designer",
            "planner",
            "experimenter",
            "evaluator",
            "visualizer",
            "writer",
            "podcaster",
            "video_producer",
            "publisher",
        }
        missing = sorted(required - set(self.agents))
        if missing:
            raise ValueError(f"Missing required agents: {', '.join(missing)}")
        for name, agent in self.agents.items():
            unknown_routes = [route for route in agent.routes() if route not in self.models]
            if unknown_routes:
                raise ValueError(
                    f"Agent '{name}' references unknown model routes: {', '.join(unknown_routes)}"
                )
        unknown_judges = sorted(set(self.search.judges) - set(self.agents))
        if unknown_judges:
            raise ValueError(f"Unknown judge agents: {', '.join(unknown_judges)}")
        if self.human.mode not in {"off", "cli", "file"}:
            raise ValueError("human.mode must be one of: off, cli, file")
        allowed_checkpoints = {"idea", "plan", "results", "publication"}
        unknown_checkpoints = sorted(set(self.human.checkpoints) - allowed_checkpoints)
        if unknown_checkpoints:
            raise ValueError(f"Unknown human checkpoints: {', '.join(unknown_checkpoints)}")
        if self.execution.enabled and self.execution.agent not in self.agents:
            raise ValueError(f"Unknown execution agent: {self.execution.agent}")
        result_path = Path(self.execution.result_file)
        if result_path.is_absolute() or ".." in result_path.parts:
            raise ValueError("execution.result_file must stay inside the project workspace")
        if self.execution.target and self.execution.target not in self.compute:
            raise ValueError(f"Unknown compute target: {self.execution.target}")
        for label, value in (
            ("media.podcast_output", self.media.podcast_output),
            ("media.video_output", self.media.video_output),
        ):
            media_path = Path(value)
            if media_path.is_absolute() or ".." in media_path.parts:
                raise ValueError(f"{label} must stay inside the project workspace")
        if self.web.host != "127.0.0.1":
            raise ValueError(
                "web.host must be 127.0.0.1; use an authenticated reverse proxy for remote access"
            )

    def agent(self, name: str) -> AgentRoute:
        try:
            return self.agents[name]
        except KeyError as error:
            raise KeyError(f"Unknown agent role '{name}'") from error

    def model_for_agent(self, name: str, route_index: int = 0) -> ModelRoute:
        routes = self.agent(name).routes()
        return self.models[routes[route_index % len(routes)]]

    def with_human_mode(self, mode: Optional[str]) -> "OpenFARSConfig":
        if mode is None:
            return self
        human = HumanConfig(
            mode=mode,
            checkpoints=self.human.checkpoints,
            packet_candidates=self.human.packet_candidates,
        )
        updated = OpenFARSConfig(
            models=self.models,
            agents=self.agents,
            search=self.search,
            human=human,
            evidence=self.evidence,
            execution=self.execution,
            media=self.media,
            leaderboards=self.leaderboards,
            web=self.web,
            release=self.release,
            compute=self.compute,
            runtime=self.runtime,
            source_path=self.source_path,
        )
        updated.validate()
        return updated


def _string_list(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a YAML list of command arguments")
    return [str(item) for item in value]
