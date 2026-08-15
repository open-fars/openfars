from pathlib import Path

from openfars.config import OpenFARSConfig


def test_frontier_profile_routes_explorer_across_model_families():
    config = OpenFARSConfig.load(Path(__file__).parents[1] / "openfars.yaml")
    routes = config.agent("explorer").routes()
    assert routes == ["claude_opus", "gpt56_sol", "gemini_flash", "deepseek_v4"]
    assert config.model_for_agent("experimenter").backend == "deepseek-harness"
    assert config.release.github_account == "Dingrui-Wang"
    assert config.release.github_owner == "open-fars"
