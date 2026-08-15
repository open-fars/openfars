from __future__ import annotations

import json
from dataclasses import replace

import pytest

from openfars.config import HumanConfig
from openfars.human import HumanDecisionRequired, write_decision
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


def _handoffs(workspace):
    records = []
    for path in sorted(workspace.path("handoffs").glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records
