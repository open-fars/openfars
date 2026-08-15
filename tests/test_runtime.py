from __future__ import annotations

from openfars.models import ModelRouter
from openfars.runtime import PluginRuntime, ResearchPlugin, StageResult
from openfars.workspace import Workspace


class EchoPlugin(ResearchPlugin):
    name = "echo"

    def run(self, context, payload):
        context.workspace.write_json("artifacts/echo.json", payload)
        return StageResult(payload, "echoed", ["artifacts/echo.json"])


def test_waterfall_hook_and_scoped_plugin_lifecycle(offline_config):
    workspace = Workspace(offline_config.runtime.output_dir, "runtime-test")
    router = ModelRouter(offline_config, workspace)
    runtime = PluginRuntime(offline_config, workspace, router)
    runtime.mount(EchoPlugin())
    runtime.on(
        "stage.before",
        lambda event: {**event, "input": {**event["input"], "intercepted": True}},
    )

    result = runtime.run("echo", {"value": 1})
    runtime.unmount("echo")

    assert result.data == {"value": 1, "intercepted": True}
    assert workspace.read_json("artifacts/echo.json")["intercepted"] is True
    event_types = [event["type"] for event in _events(workspace)]
    assert "plugin.mounted" in event_types
    assert "agent.handoff" in event_types
    assert "plugin.unmounted" in event_types


def _events(workspace):
    return [
        __import__("json").loads(line) for line in workspace.read_text("events.jsonl").splitlines()
    ]
