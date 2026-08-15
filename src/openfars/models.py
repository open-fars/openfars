from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .config import AgentRoute, ModelRoute, OpenFARSConfig
from .workspace import Workspace

Message = Mapping[str, str]


class ModelError(RuntimeError):
    pass


class Backend(ABC):
    @abstractmethod
    def complete(
        self,
        route: ModelRoute,
        messages: Sequence[Message],
        context: Mapping[str, Any],
    ) -> str:
        raise NotImplementedError

    def close(self) -> None:
        """Release optional long-lived backend resources."""
        return None


class LiteLLMBackend(Backend):
    """Uniform access to hosted, gateway, and local OpenAI-compatible models."""

    def complete(
        self,
        route: ModelRoute,
        messages: Sequence[Message],
        context: Mapping[str, Any],
    ) -> str:
        try:
            import litellm
        except ImportError as error:
            raise ModelError("Install the 'models' extra to use LiteLLM backends") from error

        kwargs: Dict[str, Any] = {
            "model": route.model,
            "messages": list(messages),
            "max_tokens": route.max_tokens,
            "timeout": route.timeout,
            **dict(route.extra),
        }
        if route.temperature is not None:
            kwargs["temperature"] = route.temperature
        if route.api_key_env:
            api_key = os.getenv(route.api_key_env)
            if not api_key:
                raise ModelError(
                    f"Model route '{route.name}' requires environment variable {route.api_key_env}"
                )
            kwargs["api_key"] = api_key
        api_base = route.resolved_api_base()
        if api_base:
            kwargs["api_base"] = api_base
        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
        except Exception as error:
            raise ModelError(f"Model route '{route.name}' failed: {error}") from error
        if not content:
            raise ModelError(f"Model route '{route.name}' returned no text")
        return str(content)


class DeepSeekHarnessBackend(Backend):
    """DeepSeek Harness SDK adapter for tool-using coding and experiment agents."""

    _environment_lock = threading.Lock()

    def __init__(self, cordis: Optional[Path] = None):
        self.cordis = cordis or Path(__file__).with_name("configs") / "deepseek.cordis.yml"
        self._clients: Dict[tuple[str, str, str], Any] = {}

    def complete(
        self,
        route: ModelRoute,
        messages: Sequence[Message],
        context: Mapping[str, Any],
    ) -> str:
        try:
            from deepseek_harness import DeepSeekHarness
        except ImportError as error:
            raise ModelError(
                "Install the 'harness' extra to use the DeepSeek Harness backend"
            ) from error

        workspace_dir = Path(str(context.get("workspace_dir", ""))).resolve()
        session_root = Path(str(context.get("session_root", ""))).resolve()
        if not workspace_dir.is_dir():
            raise ModelError("DeepSeek Harness requires an existing workspace_dir")
        session_root.mkdir(parents=True, exist_ok=True)
        session_id = str(context.get("session_id") or "openfars-coder")
        prompt = "\n\n".join(message.get("content", "") for message in messages)

        # The published minimal Cordis composition reads these settings from the
        # environment. Serialize this short critical section to avoid cross-run leaks.
        with self._environment_lock:
            previous: Dict[str, Optional[str]] = {}
            updates = {
                "DSH_CWD": str(workspace_dir),
                "DSH_SESSION_ROOT": str(session_root),
                "DSH_MODEL": route.model,
                "DSH_SYSTEM_PROMPT": messages[0].get("content", "") if messages else "",
            }
            if route.api_key_env and route.api_key_env != "DEEPSEEK_API_KEY":
                value = os.getenv(route.api_key_env)
                if not value:
                    raise ModelError(f"Model route '{route.name}' requires {route.api_key_env}")
                updates["DEEPSEEK_API_KEY"] = value
            api_base = route.resolved_api_base()
            if api_base:
                updates["DEEPSEEK_BASE_URL"] = api_base
            for key, value in updates.items():
                previous[key] = os.environ.get(key)
                os.environ[key] = value
            client_key = (route.name, str(workspace_dir), str(session_root))
            try:
                harness = self._clients.get(client_key)
                if harness is None:
                    harness = DeepSeekHarness(
                        provider=route.provider,
                        model=route.model,
                        max_tokens=route.max_tokens,
                        cwd=str(workspace_dir),
                        session_root=str(session_root),
                        cordis=str(self.cordis.resolve()),
                    )
                    harness.__enter__()
                    self._clients[client_key] = harness
                # Reusing the entered harness preserves its PTY/process scope across
                # experiment iterations; session_root still makes the transcript durable.
                result = harness.run(prompt, session_id=session_id)
            except Exception as error:
                failed = self._clients.pop(client_key, None)
                if failed is not None:
                    with suppress(Exception):
                        failed.__exit__(type(error), error, error.__traceback__)
                raise ModelError(
                    f"DeepSeek Harness route '{route.name}' failed: {error}"
                ) from error
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        if not result.final_response:
            raise ModelError("DeepSeek Harness returned no final response")
        return str(result.final_response)

    def close(self) -> None:
        with self._environment_lock:
            clients = list(self._clients.values())
            self._clients.clear()
            for harness in reversed(clients):
                # Cleanup must not hide the research result or a pending human gate.
                with suppress(Exception):
                    harness.__exit__(None, None, None)


class MockBackend(Backend):
    """Deterministic, offline backend for smoke tests and the zero-key demo."""

    def complete(
        self,
        route: ModelRoute,
        messages: Sequence[Message],
        context: Mapping[str, Any],
    ) -> str:
        kind = str(context.get("response_kind", "text"))
        operator = str(context.get("operator", "counterfactual"))
        digest = hashlib.sha256(
            (operator + "|" + "|".join(message.get("content", "") for message in messages)).encode()
        ).hexdigest()[:8]
        if kind == "idea":
            return json.dumps(
                {
                    "title": f"{operator.title()} hypothesis {digest}",
                    "hypothesis": f"A {operator} intervention produces a measurable gain over the strongest baseline.",
                    "mechanism": "It changes the information bottleneck rather than only increasing scale.",
                    "test": "Run a preregistered ablation against matched-compute baselines.",
                    "falsifier": "Reject if the confidence interval includes the minimum useful effect.",
                    "assumptions": [
                        "The metric reflects the target behavior",
                        "Compute is matched",
                    ],
                    "paradigm": operator.split()[0],
                    "resource_profile": "single-node",
                }
            )
        if kind == "score":
            offset = int(digest[:2], 16) % 3
            return json.dumps(
                {
                    "novelty": 6 + offset,
                    "impact": 7,
                    "feasibility": 8,
                    "falsifiability": 9,
                    "evidence": 5,
                    "fatal_flaw": "",
                    "reason": "Offline demonstration score; replace mock routes for real evaluation.",
                }
            )
        if kind == "plan":
            return json.dumps(
                {
                    "objective": "Test the selected hypothesis with matched compute.",
                    "baselines": ["current method", "parameter-matched control"],
                    "experiments": [
                        {"name": "pilot", "purpose": "validate instrumentation"},
                        {"name": "main", "purpose": "estimate the treatment effect"},
                        {"name": "ablation", "purpose": "test the claimed mechanism"},
                    ],
                    "metrics": ["primary outcome", "runtime", "variance across seeds"],
                    "stop_conditions": ["three failed pilots", "resource budget exceeded"],
                    "resources": {"gpus": 1, "estimated_hours": 1},
                }
            )
        if kind == "direction":
            return json.dumps(
                {
                    "question": "Which causal intervention yields a reproducible improvement?",
                    "scope": ["computational experiments", "matched compute"],
                    "constraints": ["falsifiable", "reproducible", "bounded budget"],
                    "success_definition": "A replicated effect over a preregistered baseline.",
                    "non_goals": ["benchmark-only optimization without mechanism"],
                }
            )
        if kind == "landscape":
            return json.dumps(
                {
                    "consensus": ["Scale is not a substitute for controlled evaluation"],
                    "contradictions": ["Reported gains may depend on unmatched compute"],
                    "gaps": ["Mechanism-level ablations are missing"],
                    "opportunities": ["Test the bottleneck with a minimal intervention"],
                    "evidence_ids": [],
                }
            )
        if kind == "critique":
            return json.dumps(
                {
                    "fatal_risks": ["The claimed mechanism may be confounded by compute"],
                    "disagreements": ["Novelty remains unverified without full-text review"],
                    "cheap_falsifiers": ["Run a parameter- and compute-matched ablation"],
                    "recommended_candidate_id": "",
                    "human_attention": ["Choose the acceptable risk/budget frontier"],
                }
            )
        if kind == "task":
            return json.dumps(
                {
                    "research_question": "Does the intervention beat matched-compute controls?",
                    "hypothesis": "The selected mechanism improves the primary metric.",
                    "independent_variable": "intervention",
                    "dependent_variables": ["primary metric", "runtime", "variance"],
                    "controls": ["matched-compute baseline"],
                    "decision_rule": "Advance only if the effect replicates across seeds.",
                    "budget": {"gpus": 1, "hours": 1},
                }
            )
        if kind == "evaluation":
            return json.dumps(
                {
                    "verdict": "stop",
                    "quality": 0,
                    "reason": "No real experiment was executed by the offline backend.",
                    "next_step": "Configure an execution backend.",
                    "claim_status": "unsupported",
                }
            )
        if kind == "visualization":
            return json.dumps(
                {
                    "charts": [
                        {
                            "title": "Experiment metric by iteration",
                            "mark": "line",
                            "x": "iteration",
                            "y": "metric",
                            "claim": "Show observations without extrapolation.",
                        }
                    ],
                    "warnings": ["No experimental metrics were available in offline mode"],
                }
            )
        if kind == "podcast":
            return json.dumps(
                {
                    "title": "OpenFARS Research Brief",
                    "disclosure": "This episode was generated with AI and reports no completed experiment.",
                    "speakers": ["Host", "Researcher"],
                    "turns": [
                        {"speaker": "Host", "text": "What question did the project test?"},
                        {
                            "speaker": "Researcher",
                            "text": "This offline demo did not run an experiment.",
                        },
                    ],
                    "show_notes": [],
                }
            )
        if kind == "video":
            return json.dumps(
                {
                    "title": "OpenFARS Research Brief",
                    "format": "16:9",
                    "disclosure": "AI-generated storyboard",
                    "scenes": [
                        {
                            "duration_seconds": 6,
                            "narration": "A testable idea is only the start.",
                            "visual": "Show the evidence-to-experiment pipeline.",
                            "evidence_refs": [],
                        }
                    ],
                }
            )
        if kind == "release":
            return json.dumps(
                {
                    "summary": "Reproducible OpenFARS research bundle.",
                    "limitations": ["No real experiment was executed in offline mode"],
                    "recommended_license_review": True,
                    "release_notes": "Inspect all artifacts before publication.",
                }
            )
        if kind == "experiment":
            return json.dumps(
                {
                    "success": False,
                    "status": "not_executed",
                    "summary": "Mock backend generated no executable experiment.",
                    "metrics": {},
                    "artifacts": [],
                }
            )
        if kind == "paper":
            return (
                "# Offline OpenFARS Demonstration\n\n"
                "## Abstract\nThis artifact demonstrates the orchestration path; it is not a scientific result.\n\n"
                "## Methods\nCandidates were generated with quality-diversity search and gated evaluation.\n\n"
                "## Results\nNo experiment was executed.\n\n"
                "## Limitations\nConfigure real model routes and an execution backend before drawing conclusions.\n"
            )
        return f"Mock response {digest}"


class ModelRouter:
    def __init__(
        self,
        config: OpenFARSConfig,
        workspace: Workspace,
        backends: Optional[Mapping[str, Backend]] = None,
    ):
        self.config = config
        self.workspace = workspace
        self.backends: Dict[str, Backend] = {
            "litellm": LiteLLMBackend(),
            "deepseek-harness": DeepSeekHarnessBackend(),
            "mock": MockBackend(),
        }
        if backends:
            self.backends.update(backends)

    def complete(
        self,
        agent_name: str,
        prompt: str,
        *,
        response_kind: str = "text",
        context: Optional[Mapping[str, Any]] = None,
        route_index: int = 0,
    ) -> str:
        agent: AgentRoute = self.config.agent(agent_name)
        route = self.config.model_for_agent(agent_name, route_index)
        try:
            backend = self.backends[route.backend]
        except KeyError as error:
            raise ModelError(f"Unknown model backend '{route.backend}'") from error
        messages: List[Message] = []
        if agent.system_prompt:
            messages.append({"role": "system", "content": agent.system_prompt})
        messages.append({"role": "user", "content": prompt})
        merged_context: Dict[str, Any] = {
            "response_kind": response_kind,
            "workspace_dir": str(self.workspace.project_dir),
            "session_root": str(self.workspace.path("sessions")),
            "session_id": f"{self.workspace.project_id}-{agent_name}",
        }
        if context:
            merged_context.update(context)
        self.workspace.append_event(
            "model.request",
            {
                "agent": agent_name,
                "route": route.name,
                "backend": route.backend,
                "model": route.model,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            },
        )
        text = backend.complete(route, messages, merged_context)
        self.workspace.append_event(
            "model.response",
            {
                "agent": agent_name,
                "route": route.name,
                "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "characters": len(text),
            },
        )
        return text

    def complete_json(
        self,
        agent_name: str,
        prompt: str,
        *,
        response_kind: str,
        context: Optional[Mapping[str, Any]] = None,
        route_index: int = 0,
    ) -> Dict[str, Any]:
        raw = self.complete(
            agent_name,
            prompt,
            response_kind=response_kind,
            context=context,
            route_index=route_index,
        )
        try:
            parsed = json.loads(_extract_json(raw))
        except (json.JSONDecodeError, ValueError) as error:
            raise ModelError(
                f"Agent '{agent_name}' returned invalid JSON for {response_kind}"
            ) from error
        if not isinstance(parsed, dict):
            raise ModelError(f"Agent '{agent_name}' must return a JSON object")
        return parsed

    def close(self) -> None:
        seen: set[int] = set()
        for backend in self.backends.values():
            if id(backend) not in seen:
                backend.close()
                seen.add(id(backend))


def _extract_json(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    return stripped[start : end + 1]
