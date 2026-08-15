from __future__ import annotations

import pytest

from openfars.config import ComputeTarget
from openfars.release import PublicationError, Publisher
from openfars.remote import RemoteError, SSHExecutor, _under
from openfars.workspace import Workspace


def test_workspace_and_remote_paths_reject_traversal(tmp_path):
    workspace = Workspace(tmp_path, "safe")
    with pytest.raises(ValueError):
        workspace.path("../escape")
    with pytest.raises(RemoteError):
        _under("/data/project", "../escape")


def test_compute_public_description_omits_private_key(tmp_path, monkeypatch):
    key = tmp_path / "id_ed25519_test"
    key.write_text("not-a-real-key", encoding="utf-8")
    target = ComputeTarget(name="gpu", host="example.test", user="root", identity_file=str(key))
    monkeypatch.setattr("openfars.remote.shutil.which", lambda _: "/usr/bin/ssh")
    public = SSHExecutor(target).public_description()
    assert "identity" not in json_keys(public)
    assert str(key) not in str(public)


def test_remote_sync_excludes_wandb_credentials():
    assert "wandb_config.yml" in SSHExecutor._SYNC_EXCLUDES
    assert ".env" in SSHExecutor._SYNC_EXCLUDES


def test_github_publication_refuses_wrong_account(offline_config, monkeypatch):
    workspace = Workspace(offline_config.runtime.output_dir, "publish-test")
    workspace.write_json(
        "release/manifest.json", {"archive": str(workspace.write_text("release/a.zip", "x"))}
    )
    monkeypatch.setenv(offline_config.release.github_token_env, "secret")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"login": "someone-else"}

    monkeypatch.setattr("openfars.release.requests.get", lambda *args, **kwargs: Response())
    with pytest.raises(PublicationError, match="Dingrui-Wang"):
        Publisher(offline_config.release, workspace).publish(confirm=True, github=True)


def json_keys(value):
    return " ".join(value.keys())
