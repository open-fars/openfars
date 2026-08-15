from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .models import ModelRouter
from .workspace import Workspace


class VisualizationAgent:
    """Separates semantic chart intent from deterministic data rendering."""

    def __init__(self, router: ModelRouter, workspace: Workspace):
        self.router = router
        self.workspace = workspace

    def run(
        self,
        task: Mapping[str, Any],
        iterations: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        prompt = f"""Design honest scientific figures for this research task and its observed iterations.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Iterations:
{json.dumps(list(iterations), ensure_ascii=False, indent=2)}

Return only JSON with charts (title, mark, x, y, color, claim, evidence_fields,
caption) and warnings. Prefer declarative, data-linked plots. Never request a chart
whose claim is unsupported, hide failed runs, truncate axes deceptively, or invent values.
"""
        spec = self.router.complete_json("visualizer", prompt, response_kind="visualization")
        self.workspace.write_json("visualizations/spec.json", spec)
        self._render_iteration_svg(iterations)
        return spec

    def _render_iteration_svg(self, iterations: Sequence[Mapping[str, Any]]) -> Path:
        numeric = []
        for index, item in enumerate(iterations, start=1):
            metrics = item.get("result", {}).get("metrics", {})
            for name, value in metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric.append((index, str(name), float(value)))
        width, height = 760, 420
        if not numeric:
            body = '<text x="30" y="70" fill="#64748b">No numeric experimental metrics available.</text>'
        else:
            values = [value for _, _, value in numeric]
            low, high = min(values), max(values)
            span = high - low or 1.0
            elements = []
            for iteration, name, value in numeric:
                x = 70 + (iteration - 1) * (620 / max(1, len(iterations) - 1))
                y = 340 - ((value - low) / span) * 260
                elements.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#ff6b4a">'
                    f"<title>{html.escape(name)}: {value}</title></circle>"
                )
            body = "\n".join(elements)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#ffffff"/><line x1="70" y1="340" x2="700" y2="340" stroke="#94a3b8"/>
<line x1="70" y1="60" x2="70" y2="340" stroke="#94a3b8"/>
<text x="330" y="390" fill="#334155">Experiment iteration</text>{body}</svg>"""
        return self.workspace.write_text("visualizations/iterations.svg", svg)
