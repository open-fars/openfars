from __future__ import annotations

import json
from dataclasses import replace

from openfars.config import ComputeTarget, ExecutionConfig
from openfars.evaluation import ResultEvaluator
from openfars.execution import ExperimentRunner
from openfars.models import ModelRouter
from openfars.remote import RemoteResult
from openfars.workspace import Workspace


def test_remote_result_contract_is_authoritative(offline_config, monkeypatch):
    class FakeSSH:
        def __init__(self, target, workspace=None):
            self.target = target
            self.workspace = workspace

        def push(self, *_):
            return None

        def run(self, command, **_):
            return RemoteResult(0, "remote-ok\n" if not command.startswith("rm ") else "", "")

        def pull(self, _, local):
            result = local / "artifacts/iterations/001/result.json"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(
                json.dumps(
                    {
                        "success": True,
                        "status": "completed",
                        "summary": "GPU experiment completed.",
                        "metrics": {"accuracy": 0.9},
                        "artifacts": [],
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("openfars.execution.SSHExecutor", FakeSSH)
    config = _remote_config(offline_config)
    workspace = Workspace(config.runtime.output_dir, "remote-result-test")
    result = ExperimentRunner(config, ModelRouter(config, workspace), workspace).run({}, {})

    assert result["status"] == "completed"
    assert result["result_origin"] == "remote"
    assert result["execution_target"] == "gpu"
    assert result["remote_output_dir"] == "/tmp/openfars-output/remote-result-test"
    assert result["metrics"] == {"accuracy": 0.9}


def test_failed_remote_command_cannot_report_success(offline_config, monkeypatch):
    class FailingSSH:
        def __init__(self, target, workspace=None):
            pass

        def push(self, *_):
            return None

        def run(self, command, **_):
            return RemoteResult(0 if command.startswith("rm ") else 9, "", "failed")

        def pull(self, _, local):
            result = local / "artifacts/iterations/001/result.json"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(
                json.dumps(
                    {
                        "success": True,
                        "status": "completed",
                        "summary": "Stale success must be rejected.",
                        "metrics": {"accuracy": 1.0},
                        "artifacts": [],
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("openfars.execution.SSHExecutor", FailingSSH)
    config = _remote_config(offline_config)
    workspace = Workspace(config.runtime.output_dir, "remote-failure-test")
    result = ExperimentRunner(config, ModelRouter(config, workspace), workspace).run({}, {})

    assert result["success"] is False
    assert result["status"] == "remote_command_failed"
    assert result["remote_returncode"] == 9


def test_infrastructure_smoke_is_never_scientific_evidence(offline_config):
    workspace = Workspace(offline_config.runtime.output_dir, "smoke-evaluation-test")
    evaluation = ResultEvaluator(ModelRouter(offline_config, workspace)).evaluate(
        {},
        {},
        {"status": "infrastructure_smoke", "success": True},
        [],
    )

    assert evaluation["verdict"] == "stop"
    assert evaluation["claim_status"] == "unsupported"
    assert evaluation["source"] == "deterministic_guard"


def _remote_config(offline_config):
    return replace(
        offline_config,
        execution=ExecutionConfig(
            enabled=True,
            agent="experimenter",
            result_file="experiment_result.json",
            target="gpu",
            command="python code/experiment.py",
            max_iterations=2,
        ),
        compute={
            "gpu": ComputeTarget(
                name="gpu",
                host="gpu.example",
                user="researcher",
                workdir="/data/openfars",
            )
        },
    )
