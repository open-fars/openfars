from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Sequence

from .config import OpenFARSConfig
from .models import ModelError, ModelRouter, _extract_json
from .remote import SSHExecutor
from .workspace import Workspace


class ExperimentRunner:
    def __init__(self, config: OpenFARSConfig, router: ModelRouter, workspace: Workspace):
        self.config = config
        self.router = router
        self.workspace = workspace

    def run(
        self,
        task: Mapping[str, Any],
        plan: Mapping[str, Any],
        human_feedback: str = "",
        *,
        iteration: int = 1,
        history: Sequence[Mapping[str, Any]] = (),
    ) -> Dict[str, Any]:
        iteration_dir = f"artifacts/iterations/{iteration:03d}"
        result_contract = f"{iteration_dir}/result.json"
        if not self.config.execution.enabled:
            result = {
                "success": False,
                "status": "not_executed",
                "summary": "Execution is disabled. No metrics were simulated.",
                "metrics": {},
                "artifacts": [],
                "iteration": iteration,
            }
            self.workspace.write_json(result_contract, result)
            return result

        prompt = f"""Implement and run the approved research experiment inside this workspace.

Research task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Approved plan:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Human steering:
{human_feedback or "none"}

This is iteration {iteration}. Previous iteration evidence:
{json.dumps(list(history), ensure_ascii=False, indent=2)}

Requirements:
1. Inspect the workspace before changing it.
2. Put source code under code/ and never embed credentials.
3. Start with a cheap smoke test, then run only the approved experiment.
4. Preserve logs, plots, and checkpoints as artifacts.
5. Write the final machine-readable result to {result_contract} with keys:
   success, status, summary, metrics, artifacts, failures.
6. Never invent a metric. A failed run is valid evidence.
7. If iterating, change only the evaluator-requested variable and retain prior outputs.
"""
        response = self.router.complete(
            self.config.execution.agent,
            prompt,
            response_kind="experiment",
        )
        response_path = f"{iteration_dir}/agent_response.md"
        self.workspace.write_text(response_path, response)

        if self.config.execution.target:
            self._run_remote(iteration)

        candidate_paths = [
            self.workspace.path(result_contract),
            self.workspace.path(self.config.execution.result_file),
            self.workspace.path(f"artifacts/{self.config.execution.result_file}"),
        ]
        for path in candidate_paths:
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    result = json.load(handle)
                break
        else:
            try:
                result = json.loads(_extract_json(response))
            except (json.JSONDecodeError, ValueError):
                result = {
                    "success": False,
                    "status": "missing_result_contract",
                    "summary": response[-2000:],
                    "metrics": {},
                    "artifacts": [response_path],
                }
        if not isinstance(result, dict):
            raise ModelError("Experiment result must be a JSON object")
        result.setdefault("success", False)
        result.setdefault("status", "unknown")
        result.setdefault("metrics", {})
        result.setdefault("artifacts", [])
        result["iteration"] = iteration
        self.workspace.write_json(result_contract, result)
        return result

    def _run_remote(self, iteration: int) -> None:
        target_name = self.config.execution.target
        target = self.config.compute[target_name]
        executor = SSHExecutor(target, workspace=self.workspace)
        remote_project = f"projects/{self.workspace.project_id}"
        executor.push(self.workspace.project_dir, remote_project)
        command = self.config.execution.command
        if not command:
            raise ValueError("execution.command is required for SSH execution")
        result = executor.run(
            command,
            cwd=f"{target.workdir.rstrip('/')}/{remote_project}",
            timeout=self.config.execution.timeout,
        )
        root = f"artifacts/iterations/{iteration:03d}"
        self.workspace.write_text(f"{root}/remote.stdout.log", result.stdout)
        self.workspace.write_text(f"{root}/remote.stderr.log", result.stderr)
        self.workspace.write_json(f"{root}/remote.exit.json", {"returncode": result.returncode})
        executor.pull(remote_project, self.workspace.path(f"{root}/remote"))
