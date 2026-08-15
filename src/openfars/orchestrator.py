from __future__ import annotations

import uuid
from typing import Any, Dict, Mapping, Optional, Sequence

from .agents import default_agent_plugins
from .config import OpenFARSConfig
from .evaluation import ResultEvaluator
from .execution import ExperimentRunner
from .human import HumanGate
from .literature import LiteratureClient
from .media import MediaProducer
from .models import ModelRouter
from .release import ReleaseBuilder
from .report import write_report
from .runtime import PluginRuntime
from .search import IdeaSearch
from .visualization import VisualizationAgent
from .workspace import Workspace


class ResearchOrchestrator:
    """Resumable control plane for the complete evidence-to-release workflow."""

    def __init__(self, config: OpenFARSConfig):
        self.config = config

    def run(
        self,
        topics: Sequence[str],
        *,
        project_id: Optional[str] = None,
    ) -> Workspace:
        project_id = project_id or f"research-{uuid.uuid4().hex[:8]}"
        workspace = Workspace(self.config.runtime.output_dir, project_id)
        router = ModelRouter(self.config, workspace)
        gate = HumanGate(self.config.human, workspace)
        state = self._load_or_create_state(workspace, project_id, topics)
        topics = state["topics"]

        literature = LiteratureClient(timeout=self.config.evidence.timeout)
        services = {
            "literature": literature,
            "idea_search": IdeaSearch(
                router,
                self.config.search,
                literature=literature if self.config.evidence.enabled else None,
                papers_per_query=self.config.evidence.papers_per_query,
            ),
            "experiment_runner": ExperimentRunner(self.config, router, workspace),
            "result_evaluator": ResultEvaluator(router),
            "visualization": VisualizationAgent(router, workspace),
            "media": MediaProducer(self.config.media, router, workspace),
            "release_builder": ReleaseBuilder(self.config.release, router, workspace),
        }
        try:
            with PluginRuntime(self.config, workspace, router, services=services) as runtime:
                for plugin in default_agent_plugins():
                    runtime.mount(plugin)
                self._install_policies(runtime)
                self._advance(runtime, gate, state, topics)
        finally:
            router.close()
        return workspace

    def _advance(
        self,
        runtime: PluginRuntime,
        gate: HumanGate,
        state: Dict[str, Any],
        topics: Sequence[str],
    ) -> None:
        workspace = runtime.workspace
        project_id = workspace.project_id

        if state["stage"] == "created":
            runtime.run("director", {"topics": topics})
            self._transition(workspace, state, "direction_ready")

        if state["stage"] == "direction_ready":
            runtime.run("librarian", {"topics": topics})
            self._transition(workspace, state, "literature_ready")

        if state["stage"] == "literature_ready":
            runtime.run("explorer", {"topics": topics})
            self._transition(workspace, state, "ideas_ready")

        if state["stage"] == "ideas_ready":
            runtime.run("critic", {})
            self._transition(workspace, state, "critique_ready")

        if state["stage"] in {"critique_ready", "waiting_idea"}:
            portfolio = workspace.read_json("artifacts/ideas.json")
            finalists = portfolio["finalists"]
            default_id = finalists[0]["id"]
            self._transition(workspace, state, "waiting_idea")
            decision = gate.decide(
                "idea",
                {
                    "project_id": project_id,
                    "candidates": finalists[: self.config.human.packet_candidates],
                    "critical_review": workspace.read_json("artifacts/critical_review.json", {}),
                },
                default_selected_id=default_id,
            )
            if decision.action == "reject":
                self._transition(workspace, state, "rejected")
                return
            selected_id = decision.selected_id or default_id
            choices = {item["id"]: item for item in portfolio["ranked"]}
            if selected_id not in choices:
                raise ValueError(f"Human selected unknown idea '{selected_id}'")
            selected = dict(choices[selected_id])
            selected.update(decision.overrides)
            workspace.write_json("artifacts/selected_idea.json", selected)
            state["human_feedback"]["idea"] = decision.feedback
            self._transition(workspace, state, "idea_approved")

        if state["stage"] == "idea_approved":
            runtime.run(
                "task_designer",
                {"human_feedback": state["human_feedback"].get("idea", "")},
            )
            self._transition(workspace, state, "task_ready")

        if state["stage"] == "task_ready":
            runtime.run("planner", {})
            self._transition(workspace, state, "plan_ready")

        if state["stage"] in {"plan_ready", "waiting_plan"}:
            plan = workspace.read_json("artifacts/plan.json")
            self._transition(workspace, state, "waiting_plan")
            decision = gate.decide("plan", {"project_id": project_id, "plan": plan})
            if decision.action == "reject":
                self._transition(workspace, state, "rejected")
                return
            plan.update(decision.overrides)
            workspace.write_json("artifacts/plan.json", plan)
            state["human_feedback"]["plan"] = decision.feedback
            state.setdefault("experiment", {"iteration": 1, "history": []})
            self._transition(workspace, state, "experimenting")

        if state["stage"] == "experimenting":
            self._run_experiment_loop(runtime, state)

        if state["stage"] in {"results_ready", "waiting_results"}:
            result = workspace.read_json("artifacts/experiment_result.json")
            evaluation = workspace.read_json("artifacts/final_evaluation.json")
            self._transition(workspace, state, "waiting_results")
            decision = gate.decide(
                "results",
                {
                    "project_id": project_id,
                    "result": result,
                    "evaluation": evaluation,
                    "iterations": len(state.get("experiment", {}).get("history", [])),
                },
            )
            if decision.action == "reject":
                self._transition(workspace, state, "rejected")
                return
            state["human_feedback"]["results"] = decision.feedback
            self._transition(workspace, state, "results_approved")

        if state["stage"] == "results_approved":
            runtime.run(
                "visualizer",
                {"iterations": state.get("experiment", {}).get("history", [])},
            )
            self._transition(workspace, state, "visualization_ready")

        if state["stage"] == "visualization_ready":
            runtime.run(
                "writer",
                {"human_feedback": state["human_feedback"].get("results", "")},
            )
            self._transition(workspace, state, "paper_ready")

        if state["stage"] == "paper_ready":
            runtime.run("podcaster", {})
            self._transition(workspace, state, "podcast_ready")

        if state["stage"] == "podcast_ready":
            runtime.run("video_producer", {})
            workspace.write_json(
                "media/manifest.json",
                {
                    "podcast": "media/podcast/package.json"
                    if workspace.path("media/podcast/package.json").exists()
                    else "disabled",
                    "video": "media/video/storyboard.json"
                    if workspace.path("media/video/storyboard.json").exists()
                    else "disabled",
                },
            )
            self._transition(workspace, state, "media_ready")

        if state["stage"] == "media_ready":
            runtime.run("publisher", {"external_write": False})
            self._transition(workspace, state, "release_ready")

        if state["stage"] in {"release_ready", "waiting_publication"}:
            self._transition(workspace, state, "waiting_publication")
            decision = gate.decide(
                "publication",
                {
                    "project_id": project_id,
                    "release": workspace.read_json("release/manifest.json", {}),
                    "citation_audit": workspace.read_json("paper/citation_audit.json", {}),
                    "note": "Approval completes the local workflow; external publishing still requires openfars publish --confirm.",
                },
            )
            if decision.action == "reject":
                self._transition(workspace, state, "rejected")
                return
            self._transition(workspace, state, "publication_approved")

        if state["stage"] == "publication_approved":
            write_report(
                workspace,
                workspace.read_json("artifacts/ideas.json"),
                workspace.read_json("artifacts/selected_idea.json"),
                workspace.read_json("artifacts/plan.json"),
                workspace.read_json("artifacts/experiment_result.json"),
            )
            self._transition(workspace, state, "complete")

    def _run_experiment_loop(self, runtime: PluginRuntime, state: Dict[str, Any]) -> None:
        workspace = runtime.workspace
        experiment = state.setdefault("experiment", {"iteration": 1, "history": []})
        history = experiment.setdefault("history", [])
        while state["stage"] == "experimenting":
            iteration = int(experiment.get("iteration", 1))
            feedback = str(state["human_feedback"].get("plan", ""))
            if history:
                feedback = "\n".join(
                    item
                    for item in [
                        feedback,
                        str(history[-1].get("evaluation", {}).get("next_step", "")),
                    ]
                    if item
                )
            result = runtime.run(
                "experimenter",
                {
                    "iteration": iteration,
                    "history": history,
                    "human_feedback": feedback,
                },
            ).data
            evaluation = runtime.run(
                "evaluator",
                {"iteration": iteration, "result": result, "history": history},
            ).data
            record = {
                "iteration": iteration,
                "result": result,
                "evaluation": evaluation,
            }
            history.append(record)
            experiment["history"] = history
            workspace.write_json("artifacts/experiment_history.json", history)
            workspace.write_json("state.json", state)
            verdict = str(evaluation.get("verdict", "stop"))
            if verdict == "iterate" and iteration < self.config.execution.max_iterations:
                experiment["iteration"] = iteration + 1
                workspace.append_event(
                    "experiment.iterate",
                    {
                        "from_iteration": iteration,
                        "next_step": evaluation.get("next_step", ""),
                    },
                )
                continue
            final_result = dict(result)
            final_result["iterations"] = iteration
            final_result["evaluation_verdict"] = verdict
            workspace.write_json("artifacts/experiment_result.json", final_result)
            workspace.write_json("artifacts/final_evaluation.json", evaluation)
            self._transition(workspace, state, "results_ready")

    def _load_or_create_state(
        self,
        workspace: Workspace,
        project_id: str,
        topics: Sequence[str],
    ) -> Dict[str, Any]:
        state = workspace.read_json("state.json", default=None)
        if state is not None:
            return state
        if not topics:
            raise ValueError("At least one research topic is required")
        state = {
            "project_id": project_id,
            "topics": list(topics),
            "stage": "created",
            "human_feedback": {},
        }
        workspace.write_json(
            "manifest.json",
            {
                "schema": "openfars.project/v2",
                "project_id": project_id,
                "topics": list(topics),
                "agents": {
                    role: {
                        "routes": agent.routes(),
                        "models": [
                            {
                                "route": route,
                                "backend": self.config.models[route].backend,
                                "model": self.config.models[route].model,
                            }
                            for route in agent.routes()
                        ],
                    }
                    for role, agent in self.config.agents.items()
                },
            },
        )
        self._transition(workspace, state, "created")
        return state

    @staticmethod
    def _install_policies(runtime: PluginRuntime) -> None:
        def external_effect_policy(event: Mapping[str, Any]) -> Mapping[str, Any]:
            if event.get("agent") == "publisher":
                payload = event.get("input", {})
                if isinstance(payload, Mapping) and payload.get("external_write"):
                    raise PermissionError(
                        "Publisher plugins may only build local bundles in the research run. "
                        "Use the explicit publish command for external writes."
                    )
            return event

        runtime.on("stage.before", external_effect_policy)

    @staticmethod
    def _transition(workspace: Workspace, state: Dict[str, Any], stage: str) -> None:
        previous = state.get("stage")
        state["stage"] = stage
        workspace.write_json("state.json", state)
        workspace.append_event("state.transition", {"from": previous, "to": stage})
