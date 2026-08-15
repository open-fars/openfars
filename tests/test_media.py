from __future__ import annotations

import sys

from openfars.config import MediaConfig
from openfars.media import MediaProducer
from openfars.models import ModelRouter
from openfars.workspace import Workspace


def test_podcast_renderer_creates_audited_binary(offline_config):
    workspace = Workspace(offline_config.runtime.output_dir, "media-render-test")
    config = MediaConfig(
        podcast_render_command=[
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                "assert Path(sys.argv[1]).is_file(); "
                "Path(sys.argv[2]).write_bytes(b'RIFF-openfars')"
            ),
            "{package}",
            "{output}",
        ],
        podcast_output="media/podcast/podcast.wav",
    )
    producer = MediaProducer(config, ModelRouter(offline_config, workspace), workspace)

    result = producer.run_podcast("# Paper", {"status": "test"}, [])

    assert result["status"] == "rendered"
    assert result["output"] == "media/podcast/podcast.wav"
    assert workspace.path(result["output"]).read_bytes() == b"RIFF-openfars"
    receipt = workspace.read_json("media/podcast/render.json")
    assert receipt["output_sha256"]
    assert "command" not in receipt
