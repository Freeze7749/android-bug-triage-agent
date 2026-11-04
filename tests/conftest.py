from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture
def sim_log():
    return ROOT / "samples" / "demo_sim_failure.log"


@pytest.fixture
def shield_log():
    return ROOT / "samples" / "shield_radio_excerpt.log"
