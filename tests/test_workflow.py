from __future__ import annotations

import json
from dataclasses import replace

import pytest

from openfars.config import EvidenceConfig, HumanConfig
from openfars.human import HumanDecisionRequired, write_decision
from openfars.literature import Paper
from openfars.orchestrator import ResearchOrchestrator
from openfars.workspace import Workspace


def test_complete_offline_workflow_preserves_no_evidence_claim(offline_config):
    workspace = ResearchOrchestrator(offline_config).run(
        ["quality-diverse scientific ideas"], project_id="workflow-test"
    )

    state = workspace.read_json("state.json")
    assert state["stage"] == "complete"
    assert [item["agent"] for item in _handoffs(workspace)] == [
        "director",
        "librarian",
        "explorer",
        "critic",
        "task_designer",
        "planner",
        "experimenter",
        "evaluator",
        "visualizer",
        "writer",
        "podcaster",
        "video_producer",
        "publisher",
    ]
    result = workspace.read_json("artifacts/experiment_result.json")
    assert result["status"] == "not_executed"
    assert result["evaluation_verdict"] == "stop"
    release = workspace.read_json("release/manifest.json")
    assert release["external_writes"] is False
    assert workspace.path("release/package/ro-crate-metadata.json").is_file()
    assert len(list(workspace.path("release/package/handoffs").glob("*.json"))) == 12


def test_explorer_manifest_contains_heterogeneous_model_pool(offline_config):
    workspace = ResearchOrchestrator(offline_config).run(
        ["model diversity"], project_id="pool-test"
    )
    explorer = workspace.read_json("manifest.json")["agents"]["explorer"]
    assert explorer["routes"] == ["mock"]


def test_human_idea_gate_resumes_from_durable_decision(offline_config):
    config = replace(
        offline_config,
        human=HumanConfig(mode="file", checkpoints=["idea"], packet_candidates=3),
    )
    orchestrator = ResearchOrchestrator(config)
    with pytest.raises(HumanDecisionRequired):
        orchestrator.run(["human steering"], project_id="human-test")

    workspace = Workspace(config.runtime.output_dir, "human-test")
    assert workspace.read_json("state.json")["stage"] == "waiting_idea"
    candidates = workspace.read_json("artifacts/ideas.json")["finalists"]
    selected = candidates[-1]["id"]
    write_decision(
        workspace,
        "idea",
        action="approve",
        selected_id=selected,
        feedback="Prefer the cheapest falsifier.",
    )

    resumed = orchestrator.run([], project_id="human-test")
    assert resumed.read_json("state.json")["stage"] == "complete"
    assert resumed.read_json("artifacts/selected_idea.json")["id"] == selected


def test_librarian_executes_model_proposed_query_expansions(offline_config, monkeypatch):
    queries = []

    class FakeLiterature:
        def __init__(self, *_, **__):
            pass

        def search(self, query, limit):
            queries.append(query)
            identity = len(queries)
            return [
                Paper(
                    id=f"W{identity}",
                    title=f"Evidence {identity}",
                    year=2026,
                    authors=["Researcher"],
                    venue="Test venue",
                    doi=None,
                    url=f"https://example.test/{identity}",
                    abstract="Controlled evidence.",
                )
            ][:limit]

    monkeypatch.setattr("openfars.orchestrator.LiteratureClient", FakeLiterature)
    config = replace(
        offline_config,
        evidence=EvidenceConfig(enabled=True, papers_per_query=2, timeout=1),
    )
    workspace = ResearchOrchestrator(config).run(
        ["iterative retrieval"], project_id="literature-expansion-test"
    )

    provenance = workspace.read_json("artifacts/literature_queries.json")
    assert "mechanism-level ablation matched compute" in provenance["executed"]
    assert "information bottleneck causal intervention" in provenance["executed"]
    assert provenance["records"] >= 3


def test_human_feedback_revises_the_idea_frontier(offline_config):
    config = replace(
        offline_config,
        human=HumanConfig(mode="file", checkpoints=["idea"], packet_candidates=3),
    )
    orchestrator = ResearchOrchestrator(config)
    with pytest.raises(HumanDecisionRequired):
        orchestrator.run(["human gradient"], project_id="idea-revision-test")

    workspace = Workspace(config.runtime.output_dir, "idea-revision-test")
    first_ids = [
        item["id"] for item in workspace.read_json("artifacts/ideas.json")["finalists"]
    ]
    write_decision(
        workspace,
        "idea",
        action="revise",
        feedback="Move toward cheaper mechanism-level falsifiers.",
    )
    with pytest.raises(HumanDecisionRequired):
        orchestrator.run([], project_id="idea-revision-test")

    second_ids = [
        item["id"] for item in workspace.read_json("artifacts/ideas.json")["finalists"]
    ]
    assert second_ids != first_ids
    assert workspace.path("artifacts/idea_revisions/001/ideas.json").is_file()
    assert workspace.path("decisions/history/idea-001.decision.json").is_file()
    assert workspace.read_json("state.json")["idea_revisions"][0]["feedback"] == (
        "Move toward cheaper mechanism-level falsifiers."
    )

    write_decision(
        workspace,
        "idea",
        action="approve",
        selected_id=second_ids[0],
    )
    completed = orchestrator.run([], project_id="idea-revision-test")
    assert completed.read_json("state.json")["stage"] == "complete"


def _handoffs(workspace):
    records = []
    for path in sorted(workspace.path("handoffs").glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records
