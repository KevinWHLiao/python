"""Pass/fail judgment for NKRO ghost-key capture."""

from __future__ import annotations

from dataclasses import dataclass

from .keycodes import names_to_vk_set, vk_to_name


@dataclass(frozen=True)
class JudgeResult:
    passed: bool
    detected: frozenset[int]
    missing: frozenset[int]
    ghost: frozenset[int]
    expected: frozenset[int]

    @property
    def detected_count(self) -> int:
        return len(self.detected)

    def missing_names(self) -> list[str]:
        return sorted(vk_to_name(v) for v in self.missing)

    def ghost_names(self) -> list[str]:
        return sorted(vk_to_name(v) for v in self.ghost)


def judge(
    detected_vks: set[int],
    expected_names: list[str],
    allowed_extra_names: list[str] | None = None,
) -> JudgeResult:
    expected = names_to_vk_set(expected_names)
    allowed = names_to_vk_set(allowed_extra_names or [])
    detected = frozenset(vk & 0xFF for vk in detected_vks)
    missing = frozenset(expected - detected)
    ghost = frozenset(detected - expected - allowed)
    return JudgeResult(
        passed=(not missing and not ghost),
        detected=detected,
        missing=missing,
        ghost=ghost,
        expected=frozenset(expected),
    )
