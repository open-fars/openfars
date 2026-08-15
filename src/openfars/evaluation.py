from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Sequence

from .models import ModelRouter


class ResultEvaluator:
    """External decision rules first; model judgment is an explanatory fallback."""

    def __init__(self, router: ModelRouter):
        self.router = router

    def evaluate(
        self,
        task: Mapping[str, Any],
        plan: Mapping[str, Any],
        result: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        status = str(result.get("status", "")).lower()
        if status == "not_executed":
            return {
                "verdict": "stop",
                "quality": 0,
                "reason": "Execution was disabled; there is no evidence to iterate on.",
                "next_step": "Configure a local, SSH, or DeepSeek Harness execution route.",
                "claim_status": "unsupported",
                "source": "deterministic_guard",
            }
        decision = result.get("decision")
        if isinstance(decision, dict) and isinstance(decision.get("passed"), bool):
            passed = decision["passed"]
            return {
                "verdict": "advance" if passed else "iterate",
                "quality": float(decision.get("score", 10 if passed else 0)),
                "reason": str(decision.get("reason", "Executable decision rule")),
                "next_step": str(decision.get("next_step", "")),
                "claim_status": "supported" if passed else "not_yet_supported",
                "source": "executable_decision_rule",
            }
        prompt = f"""Evaluate an experiment against its preregistered task and plan.

Research task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Plan and decision rule:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Observed result (never infer unreported metrics):
{json.dumps(result, ensure_ascii=False, indent=2)}

Previous iteration summaries:
{json.dumps(list(history), ensure_ascii=False, indent=2)}

Return only JSON with verdict (advance|iterate|stop), quality (0-10), reason,
next_step (one minimal change), and claim_status (supported|refuted|inconclusive).
Advance only for replicated evidence meeting the stated decision rule. Failed runs are evidence.
"""
        evaluation = self.router.complete_json("evaluator", prompt, response_kind="evaluation")
        verdict = str(evaluation.get("verdict", "stop")).lower()
        if verdict not in {"advance", "iterate", "stop"}:
            verdict = "stop"
        evaluation["verdict"] = verdict
        evaluation["source"] = "evaluator_agent"
        return evaluation
