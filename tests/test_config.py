from pathlib import Path

from jquant.config import load_config


def test_load_default_config() -> None:
    config = load_config(Path("config/tech_small_cap.toml"))

    assert config.strategy.industry_codes == ("801080", "801750", "801770")
    assert config.strategy.hold_count == 10
    assert config.costs.lot_size == 100

