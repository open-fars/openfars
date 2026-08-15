#!/usr/bin/env python3
"""Write a non-scientific result contract for SSH transport verification only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result",
        default="artifacts/iterations/001/result.json",
        help="project-relative result contract path",
    )
    args = parser.parse_args()
    relative = Path(args.result)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("--result must stay inside the current project")
    destination = (Path.cwd() / relative).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    remote_output = Path(os.environ["OPENFARS_REMOTE_OUTPUT_DIR"])
    remote_output.mkdir(parents=True, exist_ok=True)
    proof = remote_output / "transport-proof.json"
    proof.write_text(
        json.dumps(
            {
                "project_id": os.environ["OPENFARS_PROJECT_ID"],
                "iteration": int(os.environ["OPENFARS_ITERATION"]),
                "infrastructure_only": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    destination.write_text(
        json.dumps(
            {
                "success": True,
                "status": "infrastructure_smoke",
                "summary": "SSH execution and result-contract round trip succeeded; no science ran.",
                "metrics": {},
                "artifacts": [str(proof)],
                "failures": [],
                "infrastructure_only": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(destination.relative_to(Path.cwd()))


if __name__ == "__main__":
    main()
