"""Automated pytest test suite executing all 26 scenarios in examples/scenarios.jsonl."""
import json
from pathlib import Path
import pytest
from tests.harness.runner import run_scenario

SCENARIOS_FILE = Path(__file__).resolve().parent.parent / "examples" / "scenarios.jsonl"


def load_scenarios():
    lines = SCENARIOS_FILE.read_text(encoding="utf-8").strip().splitlines()
    scenarios = []
    for line in lines:
        if line.strip():
            scenarios.append(json.loads(line.strip()))
    return scenarios


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["scenario_id"])
def test_scenario(scenario):
    result = run_scenario(scenario)
    assert result.passed, f"Scenario '{result.scenario_id}' failed: {result.failed_assertions}"
