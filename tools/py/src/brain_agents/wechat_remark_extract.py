"""Extract phone / email signals from WeChat remark text (seed identifiers)."""

from __future__ import annotations

import re
from typing import Any

# China mobile (mainland): 11 digits starting 1[3-9]
_CN_MOBILE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_EMAIL = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",
)


def extract_from_remark(remark: str) -> dict[str, Any]:
    text = remark or ""
    phones = sorted(set(_CN_MOBILE.findall(text)))
    emails = sorted(set(m.group(0).lower() for m in _EMAIL.finditer(text)))
    return {"phones": phones, "emails": emails}
