"""Unit tests for CN phone normalization (no DuckDB required)."""

from __future__ import annotations

from brain_agents.identity_resolver import normalize_phone_digits


def test_domestic_11_digit_gets_86_prefix() -> None:
    assert normalize_phone_digits("13800138000") == "8613800138000"


def test_plus86_spaced_variants_normalize() -> None:
    assert normalize_phone_digits("+86 138 0013 8000") == "8613800138000"
    assert normalize_phone_digits("0086 138 0013 8000") == "8613800138000"


def test_already_canonical_china_preserved() -> None:
    assert normalize_phone_digits("8613800138000") == "8613800138000"


def test_nanp_us_not_misclassified_as_cn() -> None:
    # Strict CN mobile regex excludes 141… — US numbers must not gain a fake 86 prefix.
    assert normalize_phone_digits("+1 415 555 0123") == "14155550123"


def test_empty_and_garbage_safe() -> None:
    assert normalize_phone_digits("") == ""
    assert normalize_phone_digits("not-a-number") == ""
