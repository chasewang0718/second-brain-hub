"""Guard: tools/ps/brain-caps-d-dispatch.ps1 extension map must stay in
sync with brain_agents.{image,audio}_inbox.SUPPORTED_EXT and the PDF
convention (.pdf only).

We parse the PS hashtable literal with a regex instead of invoking PS,
so the test is cross-platform and fast.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain_agents import image_inbox, audio_inbox


PS_FILE = (
    Path(__file__).resolve().parents[2]
    / "ps"
    / "brain-caps-d-dispatch.ps1"
)


def _parse_ps_map() -> dict[str, str]:
    text = PS_FILE.read_text(encoding="utf-8")
    block_match = re.search(
        r"BrainCapsDDispatchMap\s*=\s*@\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert block_match, "dispatch map block not found in ps1"
    body = block_match.group(1)
    pairs: dict[str, str] = {}
    for line in body.splitlines():
        m = re.match(r"\s*'(\.[a-z0-9]+)'\s*=\s*'([a-z0-9-]+)'", line, re.IGNORECASE)
        if m:
            pairs[m.group(1).lower()] = m.group(2)
    assert pairs, "failed to parse any extension pairs"
    return pairs


def test_ps_map_parses():
    mp = _parse_ps_map()
    assert ".pdf" in mp
    assert mp[".pdf"] == "pdf-inbox-ingest"


def test_image_ext_coverage_matches_python():
    mp = _parse_ps_map()
    ps_image = {ext for ext, sub in mp.items() if sub == "image-inbox-ingest"}
    assert ps_image == image_inbox.SUPPORTED_EXT, (
        f"image ext drift: ps={sorted(ps_image)} vs py={sorted(image_inbox.SUPPORTED_EXT)}"
    )


def test_audio_ext_coverage_matches_python():
    mp = _parse_ps_map()
    ps_audio = {ext for ext, sub in mp.items() if sub == "audio-inbox-ingest"}
    assert ps_audio == audio_inbox.SUPPORTED_EXT, (
        f"audio ext drift: ps={sorted(ps_audio)} vs py={sorted(audio_inbox.SUPPORTED_EXT)}"
    )


def test_no_unknown_subcommands():
    mp = _parse_ps_map()
    allowed = {"pdf-inbox-ingest", "image-inbox-ingest", "audio-inbox-ingest"}
    leftover = {sub for sub in mp.values() if sub not in allowed}
    assert not leftover, f"unexpected subcommands in ps map: {leftover}"
