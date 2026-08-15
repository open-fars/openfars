from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from openfars.config import ModelRoute
from openfars.models import DeepSeekHarnessBackend


def test_deepseek_harness_reuses_entered_client(tmp_path, monkeypatch):
    created = []

    class FakeHarness:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.runs = []
            self.exits = 0
            created.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.exits += 1

        def run(self, prompt, session_id):
            self.runs.append((prompt, session_id))
            return SimpleNamespace(final_response=f"done-{len(self.runs)}")

    monkeypatch.setitem(
        sys.modules,
        "deepseek_harness",
        SimpleNamespace(DeepSeekHarness=FakeHarness),
    )
    project = tmp_path / "project"
    sessions = tmp_path / "sessions"
    project.mkdir()
    backend = DeepSeekHarnessBackend(cordis=Path("profile.yml"))
    route = ModelRoute(
        name="harness",
        backend="deepseek-harness",
        model="deepseek-test",
    )
    context = {
        "workspace_dir": str(project),
        "session_root": str(sessions),
        "session_id": "experimenter",
    }

    first = backend.complete(route, [{"role": "user", "content": "one"}], context)
    second = backend.complete(route, [{"role": "user", "content": "two"}], context)
    backend.close()

    assert (first, second) == ("done-1", "done-2")
    assert len(created) == 1
    assert created[0].runs == [("one", "experimenter"), ("two", "experimenter")]
    assert created[0].exits == 1
