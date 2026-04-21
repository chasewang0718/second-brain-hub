"""Unit tests for CN phone normalization (no DuckDB required)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from brain_agents.identity_resolver import normalize_phone_digits


def assert_eq(a: str, b: str, label: str) -> None:
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def main() -> int:
    # CN national 11-digit → E.164 CN
    assert_eq(normalize_phone_digits("13800138000"), "8613800138000", "domestic 11")
    assert_eq(normalize_phone_digits("+86 138 0013 8000"), "8613800138000", "+86 spaced")
    assert_eq(normalize_phone_digits("0086 138 0013 8000"), "8613800138000", "0086 prefix")

    # NANP: must not gain a fake 86 prefix (strict CN regex excludes 141… patterns)
    assert_eq(normalize_phone_digits("+1 415 555 0123"), "14155550123", "US NANP")

    # Already canonical CN E.164
    assert_eq(normalize_phone_digits("8613800138000"), "8613800138000", "already 86")

    print("test_identity_phone_normalize_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
