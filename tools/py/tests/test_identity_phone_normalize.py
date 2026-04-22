"""Unit tests for phone normalization (no DuckDB required).

B-ING-0.1 expanded normalization to use `phonenumbers` (Google libphonenumber)
with a configurable `default_region`. The original CN-first semantics are
preserved; new region-aware cases below cover NL / UK / DE / Ghana / NANP and
the idempotence of canonicalization, which is the contract the ingest pipeline
relies on for T2 auto-merge.
"""

from __future__ import annotations

from brain_agents.identity_resolver import normalize_phone_digits, normalize_value


# --- Existing CN behavior (B-ING-0.1 must preserve) --------------------------


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


# --- CN short-circuit must ignore default_region ----------------------------


def test_cn_short_circuit_beats_nl_region() -> None:
    # Even if caller passes NL (typical user config), a bare 11-digit CN mobile
    # still canonicalizes to 86... — the ingest saw this contract before 0.1.
    assert normalize_phone_digits("13800138000", default_region="NL") == "8613800138000"
    assert normalize_phone_digits("+86 138 0013 8000", default_region="NL") == "8613800138000"


# --- NL local mobile with region context (root cause of Hammond/Jerrel/Patricia)


def test_nl_local_mobile_with_region() -> None:
    # `06…` with no country prefix but default_region=NL → +31 6… → 316…
    assert normalize_phone_digits("0615156595", default_region="NL") == "31615156595"
    assert normalize_phone_digits("(06) 15 55 64 91", default_region="NL") == "31615556491"
    assert normalize_phone_digits("06 83 16 57 25", default_region="NL") == "31683165725"


def test_nl_international_form_unchanged() -> None:
    # Numbers that already have `+` ignore default_region → same E.164 body.
    assert normalize_phone_digits("+31615156595") == "31615156595"
    assert normalize_phone_digits("+31 6 1515 6595") == "31615156595"


def test_nl_local_and_international_are_idempotent() -> None:
    # Critical for T2 auto-merge: two shapes of the same NL number must produce
    # the same normalized value regardless of which form was stored first.
    a = normalize_phone_digits("0615156595", default_region="NL")
    b = normalize_phone_digits("+31 6 1515 6595", default_region="NL")
    assert a == b == "31615156595"


# --- Other regions pick up their own local prefixes when configured ---------


def test_uk_local_mobile_with_region() -> None:
    # UK mobile 07911 123456 → +44 7911 123456 → 447911123456
    assert normalize_phone_digits("07911 123456", default_region="GB") == "447911123456"


def test_foreign_plus_prefix_preserved() -> None:
    # Ghana / Germany / Colombia numbers (present in the user's AddressBook)
    # keep their country code no matter what default_region is.
    assert normalize_phone_digits("+233245849460", default_region="NL") == "233245849460"
    assert normalize_phone_digits("+491783711551", default_region="NL") == "491783711551"
    assert normalize_phone_digits("+573155122155", default_region="NL") == "573155122155"


# --- normalize_value threads default_region through for phone kind ----------


def test_normalize_value_phone_threads_region() -> None:
    assert normalize_value("phone", "0615156595", default_region="NL") == "31615156595"
    assert normalize_value("phone", "+31 615156595") == "31615156595"


def test_normalize_value_email_region_is_ignored() -> None:
    # Region only affects phone; email / wxid / etc. stay lowercased as before.
    assert normalize_value("email", "Foo@Example.COM", default_region="NL") == "foo@example.com"
    assert normalize_value("gmail_addr", "A.B@Gmail.com") == "a.b@gmail.com"
