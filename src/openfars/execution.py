from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Sequence

from .config import OpenFARSConfig
from .models import ModelError, ModelRouter, _extract_json
from .remote import RemoteResult, SSHExecutor
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
8. On SSH targets, put checkpoints and large artifacts under
   $OPENFARS_REMOTE_OUTPUT_DIR; use $OPENFARS_DATASETS_DIR and $OPENFARS_MODELS_DIR
   instead of copying datasets or model weights into the project.
"""
        response = self.router.complete(
            self.config.execution.agent,
            prompt,
            response_kind="experiment",
        )
        response_path = f"{iteration_dir}/agent_response.md"
        self.workspace.write_text(response_path, response)

        remote_archive: Path | None = None
        remote_execution: RemoteResult | None = None
        remote_output_dir: str | None = None
        if self.config.execution.target:
            remote_archive, remote_execution, remote_output_dir = self._run_remote(
                iteration, result_contract
            )

        candidate_paths = []
        if remote_archive is not None:
            candidate_paths.extend(
                [
                    remote_archive / result_contract,
                    remote_archive / self.config.execution.result_file,
                    remote_archive / "artifacts" / self.config.execution.result_file,
                ]
            )
        else:
            candidate_paths.extend(
                [
                    self.workspace.path(result_contract),
                    self.workspace.path(self.config.execution.result_file),
                    self.workspace.path(f"artifacts/{self.config.execution.result_file}"),
                ]
            )
        source_path: Path | None = None
        for path in candidate_paths:
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    result = json.load(handle)
                source_path = path
                break
        else:
            if remote_execution is not None:
                result = {
                    "success": False,
                    "status": "missing_remote_result_contract",
                    "summary": "The remote command produced no machine-readable result contract.",
                    "metrics": {},
                    "artifacts": [response_path, f"{iteration_dir}/remote.stdout.log"],
                }
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
        if remote_execution is not None:
            result["execution_target"] = self.config.execution.target
            result["remote_returncode"] = remote_execution.returncode
            result["remote_output_dir"] = remote_output_dir
            result["result_origin"] = "remote" if source_path is not None else "missing"
            if remote_execution.returncode != 0:
                result["success"] = False
                result["status"] = "remote_command_failed"
                failures = result.setdefault("failures", [])
                if not isinstance(failures, list):
                    failures = [str(failures)]
                    result["failures"] = failures
                failures.append(
                    f"Remote command exited with code {remote_execution.returncode}; "
                    "its metrics are not eligible for an advance verdict."
                )
        result.setdefault("success", False)
        result.setdefault("status", "unknown")
        result.setdefault("metrics", {})
        result.setdefault("artifacts", [])
        result["iteration"] = iteration
        self.workspace.write_json(result_contract, result)
        return result

    def _run_remote(
        self, iteration: int, result_contract: str
    ) -> tuple[Path, RemoteResult, str]:
        target_name = self.config.execution.target
        target = self.config.compute[target_name]
        executor = SSHExecutor(target, workspace=self.workspace)
        remote_project = f"projects/{self.workspace.project_id}"
        executor.push(self.workspace.project_dir, remote_project)
        command = self.config.execution.command
        if not command:
            raise ValueError("execution.command is required for SSH execution")
        project_output = (
            f"{target.output_dir.rstrip('/')}/{self.workspace.project_id}"
        )
        # Never accept a result copied from the controller as proof of a remote run.
        remote_result_paths = list(
            dict.fromkeys(
                [
                    result_contract,
                    self.config.execution.result_file,
                    f"artifacts/{self.config.execution.result_file}",
                ]
            )
        )
        if any(
            PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
            for path in remote_result_paths
        ):
            raise ValueError("Remote result paths must stay inside the project workspace")
        cleanup = "rm -f -- " + " ".join(shlex.quote(path) for path in remote_result_paths)
        executor.run(
            cleanup,
            cwd=f"{target.workdir.rstrip('/')}/{remote_project}",
            timeout=30,
            check=True,
        )
        environment = {
            "OPENFARS_PROJECT_ID": self.workspace.project_id,
            "OPENFARS_ITERATION": str(iteration),
            "OPENFARS_REMOTE_OUTPUT_DIR": project_output,
        }
        if target.datasets_dir:
            environment["OPENFARS_DATASETS_DIR"] = target.datasets_dir
        if target.models_dir:
            environment["OPENFARS_MODELS_DIR"] = target.models_dir
        setup = [f"mkdir -p -- {shlex.quote(project_output)}"]
        setup.extend(
            f"export {name}={shlex.quote(value)}" for name, value in environment.items()
        )
        result = executor.run(
            "\n".join([*setup, command]),
            cwd=f"{target.workdir.rstrip('/')}/{remote_project}",
            timeout=self.config.execution.timeout,
        )
        root = f"artifacts/iterations/{iteration:03d}"
        self.workspace.write_text(f"{root}/remote.stdout.log", result.stdout)
        self.workspace.write_text(f"{root}/remote.stderr.log", result.stderr)
        self.workspace.write_json(f"{root}/remote.exit.json", {"returncode": result.returncode})
        archive = self.workspace.path(f"{root}/remote")
        executor.pull(remote_project, archive)
        return archive, result, project_output
