"""Lightweight self-checks (no GUI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.judge import judge  # noqa: E402
from app.keycodes import name_to_vk, names_to_vk_set  # noqa: E402


def test_judge_pass() -> None:
    profile = json.loads(
        (ROOT / "config/profiles/infinity16_cherry_us.json").read_text(encoding="utf-8")
    )
    expected = names_to_vk_set(profile["expected_keys"])
    result = judge(expected, profile["expected_keys"], [])
    assert result.passed, (result.missing_names(), result.ghost_names())
    assert result.detected_count == 30


def test_judge_missing_and_ghost() -> None:
    profile = json.loads(
        (ROOT / "config/profiles/infinity16_cherry_us.json").read_text(encoding="utf-8")
    )
    detected = names_to_vk_set(profile["expected_keys"])
    detected.remove(name_to_vk("F1"))
    detected.add(name_to_vk("SPACE"))
    result = judge(detected, profile["expected_keys"], [])
    assert not result.passed
    assert name_to_vk("F1") in result.missing
    assert name_to_vk("SPACE") in result.ghost


def test_profiles_load() -> None:
    for path in (ROOT / "config/profiles").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"]
        assert len(data["expected_keys"]) == 30
        names_to_vk_set(data["expected_keys"])


if __name__ == "__main__":
    test_profiles_load()
    test_judge_pass()
    test_judge_missing_and_ghost()
    print("OK: all self-checks passed")
