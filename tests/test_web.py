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
        assert "Live Research Room" in page.text
        assert 'id="background-color"' in page.text
        assert 'id="office-room"' in page.text
        assert 'id="office-loading"' in page.text
        assert 'id="motion-toggle"' in page.text
        assert 'id="service-status"' in page.text
        assert 'id="handoffs"' in page.text
        assert 'id="model-routes"' in page.text
        assert 'id="new-project-form"' in page.text
        assert 'pattern="[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}"' in page.text
        assert 'type="module" src="/static/office3d.js?v=0.2.0"' in page.text
        assert "function talkPeople" not in page.text
        assert "Revise frontier" in page.text
        office3d = requests.get(f"{base}/static/office3d.js", timeout=3)
        assert office3d.status_code == 200
        assert office3d.headers["Content-Type"].startswith("text/javascript")
        assert "class Office3D" in office3d.text
        assert "const WALK_SPEED = 1.35" in office3d.text
        assert "const PERSONAL_SPACE = 0.82" in office3d.text
        assert 'this.makeLimb(root, "leftHip"' in office3d.text
        assert 'target.leftHip = -Math.PI / 2' in office3d.text
        assert 'target.leftElbow = -0.62' in office3d.text
        assert 'leftAnkle.name = "leftAnkle"' in office3d.text
        assert "addSidestep(actor, target)" in office3d.text
        assert "this.isNavigationBlocked(x, z, actor)" in office3d.text
        assert "Math.abs(localZ - 1.22) < 0.62" in office3d.text
        assert "seat.position.y = CHAIR_SEAT_Y" in office3d.text
        assert "back.position.set(0, 0.75, CHAIR_BACK_Z)" in office3d.text
        assert 'mouse.position.set(0.48, 0.925, 0.20)' in office3d.text
        assert "emissiveIntensity" in office3d.text
        assert '"IntersectionObserver" in window' in office3d.text
        etag = office3d.headers["ETag"]
        cached = requests.get(
            f"{base}/static/office3d.js", headers={"If-None-Match": etag}, timeout=3
        )
        assert cached.status_code == 304
        assert cached.headers["Cache-Control"] == "public, max-age=3600"
        three = requests.get(f"{base}/static/three.legacy.module.min.js", timeout=3)
        assert three.status_code == 200
        assert three.headers["Content-Type"].startswith("text/javascript")
        assert len(three.content) > 600_000
        assert requests.get(f"{base}/static/three.module.min.js", timeout=3).status_code == 404
        assert requests.get(f"{base}/static/THREE-LICENSE.txt", timeout=3).status_code == 404
        assert requests.get(f"{base}/api/health", timeout=3).json() == {"status": "ok"}
        models = requests.get(f"{base}/api/models", timeout=3).json()
        assert models["policy"] == "advisory_only_no_silent_route_changes"
        assert models["routes"]
        assert len(models["assignments"]) == 13
        assert models["assignments"][0]["agent"] == "director"
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
        assert len(project["agents"]) == 13
        assert {agent["name"] for agent in project["agents"]} == {
            "director",
            "librarian",
            "explorer",
            "critic",
            "task_designer",
            "planner",
            "experimenter",
            "evaluator",
            "visualizer",
            "writer",
            "podcaster",
            "video_producer",
            "publisher",
        }

        director = requests.get(f"{base}/api/projects/web-test/agents/director", timeout=3).json()
        assert director["status"] == "done"
        assert director["label"] == "Director"
        assert director["summary"]
        assert director["models"]

        asked = requests.post(
            f"{base}/api/projects/web-test/agents/director/ask",
            json={"question": "What have you completed?"},
            timeout=3,
        )
        assert asked.status_code == 200
        answer = asked.json()
        assert answer["message"]["source"] == "evidence_summary"
        assert "Director status: done" in answer["message"]["content"]
        assert [message["role"] for message in answer["chat"]] == ["user", "agent"]

        refreshed_director = requests.get(
            f"{base}/api/projects/web-test/agents/director", timeout=3
        ).json()
        assert refreshed_director["chat"] == answer["chat"]
        assert not any(
            artifact["path"].startswith("sessions/") for artifact in project["artifacts"]
        )

        unknown_agent = requests.get(f"{base}/api/projects/web-test/agents/reviewer", timeout=3)
        assert unknown_agent.status_code == 400

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
        assert resumed["state"]["human_feedback"]["idea"] == ("Prefer the lowest-cost falsifier.")
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
