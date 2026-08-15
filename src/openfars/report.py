from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .workspace import Workspace


def write_report(
    workspace: Workspace,
    portfolio: Mapping[str, Any],
    selected: Mapping[str, Any],
    plan: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Path:
    candidates = portfolio.get("ranked", [])
    points = []
    for candidate in candidates:
        scores = candidate.get("scores", {})
        x = 55 + 54 * float(scores.get("novelty", 0))
        y = 570 - 48 * float(scores.get("feasibility", 0))
        radius = 5 + 1.5 * float(scores.get("impact", 0))
        color = "#ff6b4a" if candidate.get("id") == selected.get("id") else "#36c5a5"
        points.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            f'opacity="0.78"><title>{html.escape(str(candidate.get("title")))} — '
            f"{candidate.get('composite', 0)}</title></circle>"
        )
    svg = "\n".join(points)
    payload = html.escape(
        json.dumps(
            {"selected_idea": selected, "plan": plan, "result": result},
            ensure_ascii=False,
            indent=2,
        )
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OpenFARS — {html.escape(workspace.project_id)}</title>
<style>
body{{margin:0;background:#0b1020;color:#e9eefc;font:16px system-ui;line-height:1.5}}
main{{max-width:980px;margin:auto;padding:42px 24px}}h1{{font-size:42px;margin-bottom:4px}}
.muted{{color:#94a3b8}}section{{background:#121a2e;border:1px solid #25304a;border-radius:14px;padding:22px;margin:20px 0}}
svg{{width:100%;height:auto;background:#0e1629;border-radius:10px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><main>
<h1>OpenFARS research trace</h1><div class="muted">{html.escape(workspace.project_id)}</div>
<section><h2>Selected hypothesis</h2><h3>{html.escape(str(selected.get("title", "")))}</h3>
<p>{html.escape(str(selected.get("hypothesis", "")))}</p></section>
<section><h2>Idea frontier</h2><p class="muted">Novelty →; feasibility ↑; radius = impact; orange = selected.</p>
<svg viewBox="0 0 650 620" role="img" aria-label="Idea portfolio scatter plot">
<line x1="55" y1="570" x2="620" y2="570" stroke="#60708f"/><line x1="55" y1="570" x2="55" y2="70" stroke="#60708f"/>
{svg}</svg></section>
<section><h2>Machine-readable summary</h2><pre>{payload}</pre></section>
</main></body></html>"""
    return workspace.write_text("reports/index.html", document)


def audit_citations(paper: str, ledger: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    import re

    cited = set(re.findall(r"\[(P\d+)\]", paper))
    allowed = {str(item["citation_id"]) for item in ledger}
    return {
        "cited": sorted(cited),
        "unknown": sorted(cited - allowed),
        "unused_evidence": sorted(allowed - cited),
        "passed": not (cited - allowed),
    }
