from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from openfars.config import OpenFARSConfig


@pytest.fixture
def offline_config(tmp_path: Path) -> OpenFARSConfig:
    source = Path(__file__).parents[1] / "examples" / "offline.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["runtime"]["output_dir"] = str(tmp_path / "outputs")
    raw["web"] = {"host": "127.0.0.1", "port": 0, "open_browser": False}
    target = tmp_path / "config.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return OpenFARSConfig.load(target)
