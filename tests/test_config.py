from dataclasses import replace
from pathlib import Path

import pytest

from jquant.config import load_config, validate_config


def test_load_default_config() -> None:
    config = load_config(Path("config/tech_small_cap.toml"))

    assert config.strategy.industry_codes == ("801080", "801750", "801770")
    assert "profitability" in config.strategy.enabled_filters
    assert "debt_ratio" in config.strategy.enabled_filters
    assert config.strategy.min_listing_days == 250
    assert config.strategy.max_listing_days == -1
    assert config.strategy.hold_count == 10
    assert config.costs.lot_size == 100


def test_max_listing_days_must_be_unlimited_or_at_least_minimum() -> None:
    config = load_config(Path("config/tech_small_cap.toml"))
    invalid = replace(
        config,
        strategy=replace(config.strategy, min_listing_days=250, max_listing_days=249),
    )

    with pytest.raises(ValueError, match="max_listing_days"):
        validate_config(invalid)
