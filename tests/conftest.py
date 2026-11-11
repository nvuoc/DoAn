"""Pytest configuration and shared fixtures for vanuoc tests."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def examples_dir(repo_root: Path) -> Path:
    return repo_root / "examples"


@pytest.fixture
def sample_turn_input_dict(examples_dir: Path) -> dict:
    return json.loads((examples_dir / "turn-input.json").read_text(encoding="utf-8-sig"))


@pytest.fixture
def sample_turn_result_dict(examples_dir: Path) -> dict:
    return json.loads((examples_dir / "turn-result.json").read_text(encoding="utf-8-sig"))


@pytest.fixture
def sample_delivery_event_dict(examples_dir: Path) -> dict:
    return json.loads((examples_dir / "delivery-event.json").read_text(encoding="utf-8-sig"))
