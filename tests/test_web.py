from __future__ import annotations

import threading
from dataclasses import replace

import requests

from openfars.config import HumanConfig, LeaderboardConfig
from openfars.web import OpenFARSWebServer, _refresh_leaderboards_async


def test_webui_is_loopback_and_projects_from_durable_state(offline_config):
    server = OpenFARSWebServer(offline_config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        page = requests.get(base, timeout=3)
        assert page.status_code == 200
        assert "Live research control plane" in page.text
        assert "Revise frontier" in page.text
        assert requests.get(f"{base}/api/health", timeout=3).json() == {"status": "ok"}
        models = requests.get(f"{base}/api/models", timeout=3).json()
        assert models["policy"] == "advisory_only_no_silent_route_changes"
        assert models["routes"]
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


def test_webui_human_decision_resumes_durable_run(offline_config):
    config = replace(
        offline_config,
        human=HumanConfig(mode="file", checkpoints=["idea"], packet_candidates=3),
    )
    server = OpenFARSWebServer(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        response = requests.post(
            f"{base}/api/projects",
            json={"project_id": "web-human-test", "topics": ["bounded human attention"]},
            timeout=3,
        )
        assert response.status_code == 202
        server.control._threads["web-human-test"].join(timeout=5)
        project = requests.get(f"{base}/api/projects/web-human-test", timeout=3).json()
        assert project["state"]["stage"] == "waiting_idea"
        pending = project["pending_decisions"][0]
        selected = pending["request"]["payload"]["candidates"][-1]["id"]

        decision = requests.post(
            f"{base}/api/projects/web-human-test/decisions/idea",
            json={
                "action": "approve",
                "selected_id": selected,
                "feedback": "Prefer the lowest-cost falsifier.",
                "overrides": {},
            },
            timeout=3,
        )
        assert decision.status_code == 202
        server.control._threads["web-human-test"].join(timeout=5)
        resumed = requests.get(f"{base}/api/projects/web-human-test", timeout=3).json()
        assert resumed["state"]["stage"] == "complete"
        assert resumed["state"]["human_feedback"]["idea"] == (
            "Prefer the lowest-cost falsifier."
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_webui_starts_background_leaderboard_refresh(offline_config, monkeypatch):
    refreshed = threading.Event()

    class FakeSubscriber:
        def __init__(self, config):
            pass

        def refresh(self):
            refreshed.set()

    monkeypatch.setattr("openfars.web.LeaderboardSubscriber", FakeSubscriber)
    config = replace(offline_config, leaderboards=LeaderboardConfig(enabled=True))
    thread = _refresh_leaderboards_async(config)

    assert thread is not None
    thread.join(timeout=2)
    assert refreshed.is_set()
