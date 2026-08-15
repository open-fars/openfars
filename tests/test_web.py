from __future__ import annotations

import threading

import requests

from openfars.web import OpenFARSWebServer


def test_webui_is_loopback_and_projects_from_durable_state(offline_config):
    server = OpenFARSWebServer(offline_config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        assert requests.get(f"{base}/api/health", timeout=3).json() == {"status": "ok"}
        created = requests.post(
            f"{base}/api/projects",
            json={"project_id": "web-test", "topics": ["web research control"]},
            timeout=3,
        )
        assert created.status_code == 202
        worker = server.control._threads["web-test"]
        worker.join(timeout=5)
        assert not worker.is_alive()
        project = requests.get(f"{base}/api/projects/web-test", timeout=3).json()
        assert project["state"]["stage"] == "complete"
        assert len(project["handoffs"]) == 13

        rejected = requests.post(
            f"{base}/api/projects",
            data="{}",
            headers={"Content-Type": "text/plain"},
            timeout=3,
        )
        assert rejected.status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
