#!/usr/bin/env python3
"""Offline end-to-end smoke test for the published DeepSeek Harness runtime."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from deepseek_harness import DeepSeekHarness


class _Provider(BaseHTTPRequestHandler):
    calls = 0
    requests = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        type(self).requests.append(json.loads(self.rfile.read(length)))
        type(self).calls += 1
        if self.calls in {1, 3}:
            command = (
                "export OPENFARS_HARNESS_STATE=persistent; "
                "printf harness-tool-ok > harness-proof.txt"
                if self.calls == 1
                else 'printf "$OPENFARS_HARNESS_STATE" > harness-state.txt'
            )
            events = [
                {"choices": [{"delta": {"role": "assistant", "content": None}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "openfars-smoke-call",
                                        "type": "function",
                                        "function": {
                                            "name": "bash",
                                            "arguments": json.dumps(
                                                {
                                                    "command": command,
                                                    "description": "Write the smoke-test proof",
                                                }
                                            ),
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            ]
        else:
            content = "harness-smoke-ok" if self.calls == 2 else "harness-resume-ok"
            events = [
                {"choices": [{"delta": {"role": "assistant", "content": content}}]},
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 3},
                },
            ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *_: object) -> None:
        return


def main() -> None:
    config = Path(__file__).parents[1] / "src/openfars/configs/deepseek.cordis.yml"
    _Provider.calls = 0
    _Provider.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    previous_key = os.environ.get("DEEPSEEK_API_KEY")
    previous_base = os.environ.get("DEEPSEEK_BASE_URL")
    previous_permission = os.environ.get("DSH_PERMISSION_MODE")
    os.environ["DEEPSEEK_API_KEY"] = "sk-openfars-offline-smoke"
    os.environ["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    # The provider response and command are deterministic and the workspace is
    # temporary, so this smoke can run on CI/container hosts without user namespaces.
    os.environ["DSH_PERMISSION_MODE"] = "danger-full-access"
    try:
        with tempfile.TemporaryDirectory(prefix="openfars-harness-") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            sessions = root / "sessions"
            workspace.mkdir()
            with DeepSeekHarness(
                provider="deepseek-official",
                model="deepseek-v4-flash",
                max_tokens=1024,
                cwd=str(workspace),
                session_root=str(sessions),
                cordis=str(config.resolve()),
            ) as harness:
                result = harness.run("Run the requested smoke-test tool.", session_id="smoke")
                resumed = harness.run(
                    "Verify that the persistent Bash state survived.", session_id="smoke"
                )
            assert result.final_response == "harness-smoke-ok"
            assert resumed.final_response == "harness-resume-ok"
            proof = workspace / "harness-proof.txt"
            if not proof.is_file():
                messages = _Provider.requests[-1].get("messages", [])[-3:]
                diagnostic = [
                    {"role": item.get("role"), "content": item.get("content")}
                    for item in messages
                ]
                raise AssertionError(
                    "Harness did not execute the Bash tool: "
                    + json.dumps(diagnostic, ensure_ascii=False)
                )
            assert proof.read_text() == "harness-tool-ok"
            assert (workspace / "harness-state.txt").read_text() == "persistent"
            assert list(sessions.rglob("*.jsonl"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if previous_key is None:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        else:
            os.environ["DEEPSEEK_API_KEY"] = previous_key
        if previous_base is None:
            os.environ.pop("DEEPSEEK_BASE_URL", None)
        else:
            os.environ["DEEPSEEK_BASE_URL"] = previous_base
        if previous_permission is None:
            os.environ.pop("DSH_PERMISSION_MODE", None)
        else:
            os.environ["DSH_PERMISSION_MODE"] = previous_permission
    print("DeepSeek Harness offline smoke: OK")


if __name__ == "__main__":
    main()
