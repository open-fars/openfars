from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

import requests

from .config import LeaderboardConfig, OpenFARSConfig
from .workspace import Workspace


@dataclass(frozen=True)
class LeaderboardSource:
    name: str
    url: str
    roles: Sequence[str]
    measures: str
    parser: str = "metadata"
    api_key_env: Optional[str] = None


def source_catalog(config: LeaderboardConfig) -> Mapping[str, LeaderboardSource]:
    return {
        "artificial-analysis": LeaderboardSource(
            "artificial-analysis",
            "https://artificialanalysis.ai/api/v2/language/models/free",
            (
                "director",
                "explorer",
                "critic",
                "task_designer",
                "planner",
                "experimenter",
                "evaluator",
                "visualizer",
                "writer",
                "publisher",
            ),
            "independent intelligence, coding, agentic, price, latency and throughput indices",
            "json",
            config.artificial_analysis_key_env,
        ),
        "swe-bench": LeaderboardSource(
            "swe-bench",
            "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json",
            ("experimenter",),
            "repository-level software engineering with resolved tests",
            "json",
        ),
        "deepresearch-bench": LeaderboardSource(
            "deepresearch-bench",
            "https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/resolve/main/data/leaderboard.csv",
            ("librarian", "critic", "writer"),
            "deep-research report quality, citation completeness and factuality",
            "csv",
        ),
        "terminal-bench": LeaderboardSource(
            "terminal-bench",
            "https://www.tbench.ai/leaderboard/terminal-bench/2.0",
            ("experimenter",),
            "long-horizon terminal task success for agent-model pairs",
        ),
        "paperbench": LeaderboardSource(
            "paperbench",
            "https://raw.githubusercontent.com/openai/frontier-evals/main/project/paperbench/README.md",
            ("planner", "experimenter", "evaluator"),
            "end-to-end replication of machine-learning research papers",
        ),
        "live-research-bench": LeaderboardSource(
            "live-research-bench",
            "https://livedeepresearch.github.io/",
            ("librarian", "explorer", "writer"),
            "dynamic, search-intensive and time-sensitive research tasks",
        ),
        "artificial-analysis-media": LeaderboardSource(
            "artificial-analysis-media",
            "https://artificialanalysis.ai/data-api",
            ("visualizer", "podcaster", "video_producer"),
            "image, video and speech quality, latency and price arenas",
        ),
    }


class LeaderboardSubscriber:
    """Caches benchmark feeds; it never rewrites production model routes automatically."""

    def __init__(self, config: OpenFARSConfig):
        self.config = config
        self.workspace = Workspace(config.runtime.output_dir, "_model_registry")
        self.catalog = source_catalog(config.leaderboards)

    def refresh(self, *, force: bool = False) -> Dict[str, Any]:
        if not self.config.leaderboards.enabled:
            return {
                "schema": "openfars.leaderboards/v1",
                "status": "disabled",
                "policy": "advisory_only_no_silent_route_changes",
                "sources": [],
            }
        existing = self.workspace.read_json("leaderboards/snapshot.json", {})
        if not force and self._fresh(existing):
            return existing
        sources_by_name: Dict[str, Dict[str, Any]] = {}
        fetches = {}
        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(self.config.leaderboards.sources)))
        ) as executor:
            for name in self.config.leaderboards.sources:
                source = self.catalog.get(name)
                if source is None:
                    sources_by_name[name] = {"name": name, "status": "unknown_source"}
                    continue
                fetches[executor.submit(self._fetch, source)] = name
            for future in as_completed(fetches):
                name = fetches[future]
                try:
                    sources_by_name[name] = future.result()
                except Exception as error:
                    sources_by_name[name] = {
                        "name": name,
                        "status": "error",
                        "error": str(error),
                    }
        sources: List[Dict[str, Any]] = []
        for name in self.config.leaderboards.sources:
            sources.append(sources_by_name[name])
        # Always retain specialist subscriptions even if the user only fetches a subset.
        subscribed = [
            asdict(source)
            for source in self.catalog.values()
            if source.name not in self.config.leaderboards.sources
        ]
        snapshot = {
            "schema": "openfars.leaderboards/v1",
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "refresh_hours": self.config.leaderboards.refresh_hours,
            "policy": "advisory_only_no_silent_route_changes",
            "sources": sources,
            "catalog_only_subscriptions": subscribed,
        }
        self.workspace.write_json("leaderboards/snapshot.json", snapshot)
        self.workspace.write_text("leaderboards/report.md", self._render_report(snapshot))
        self.workspace.append_event(
            "leaderboards.refreshed",
            {
                "sources": len(sources),
                "successful": sum(item.get("status") == "ok" for item in sources),
            },
        )
        return snapshot

    def status(self) -> Dict[str, Any]:
        return self.workspace.read_json("leaderboards/snapshot.json", {})

    def _fresh(self, snapshot: Mapping[str, Any]) -> bool:
        raw = snapshot.get("refreshed_at")
        if not raw:
            return False
        try:
            refreshed = datetime.fromisoformat(str(raw))
        except ValueError:
            return False
        return datetime.now(timezone.utc) - refreshed < timedelta(
            hours=self.config.leaderboards.refresh_hours
        )

    def _fetch(self, source: LeaderboardSource) -> Dict[str, Any]:
        headers = {"User-Agent": "OpenFARS leaderboard subscriber"}
        if source.api_key_env:
            key = os.getenv(source.api_key_env)
            if not key:
                return {
                    **asdict(source),
                    "status": "skipped_missing_key",
                    "required_env": source.api_key_env,
                }
            headers["x-api-key"] = key
        try:
            response = requests.get(source.url, headers=headers, timeout=30)
            response.raise_for_status()
            body = response.content[: 10 * 1024 * 1024]
            text = body.decode(response.encoding or "utf-8", errors="replace")
            suffix = {"json": "json", "csv": "csv"}.get(source.parser, "txt")
            self.workspace.write_text(f"leaderboards/raw/{source.name}.{suffix}", text)
            records = self._parse_records(source.parser, text)
            return {
                **asdict(source),
                "status": "ok",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "records": records,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
            }
        except Exception as error:
            return {**asdict(source), "status": "error", "error": str(error)}

    @staticmethod
    def _parse_records(parser: str, text: str) -> Optional[int]:
        try:
            if parser == "json":
                data = json.loads(text)
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    return len(data["data"])
                if isinstance(data, (list, dict)):
                    return len(data)
            if parser == "csv":
                return sum(1 for _ in csv.DictReader(io.StringIO(text)))
        except (ValueError, csv.Error):
            return None
        return None

    def _render_report(self, snapshot: Mapping[str, Any]) -> str:
        lines = [
            "# OpenFARS model benchmark subscriptions",
            "",
            f"Refreshed: {snapshot.get('refreshed_at', 'never')}",
            "",
            "These feeds are advisory. Route changes require task-specific evals and human review.",
            "",
            "| Source | Roles | Measures | Status |",
            "|---|---|---|---|",
        ]
        for item in snapshot.get("sources", []):
            roles = ", ".join(item.get("roles", []))
            lines.append(
                f"| {item.get('name')} | {roles} | {item.get('measures', '')} | {item.get('status')} |"
            )
        lines.extend(
            [
                "",
                "Selection rule: public leaderboards form a prior; OpenFARS' own shadow evals,",
                "failure rate, cost, latency, and pairwise cognitive diversity determine promotion.",
                "",
            ]
        )
        return "\n".join(lines)
