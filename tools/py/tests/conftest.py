"""pytest bootstrap: ensure src/ importable + isolate DuckDB from prod (B-ING-1.5)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="session", autouse=True)
def _isolated_duckdb_path(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Redirect ``brain_memory.structured._db_path()`` to a session-scoped
    tmp DuckDB file via ``BRAIN_DB_PATH``.

    Before B-ING-1.5, tests like ``ensure_person_with_seed("T Reject A", ...)``
    wrote into the live telemetry DB, inflating prod counts (174 persons + 8
    merge_log rows) and making ``test_context_for_meeting_markdown_contains_
    shared_identifier_section`` randomly collide with a real "Alice Klamer"
    in the prod person list.

    Scope is session-level so schema migration only runs once per pytest run
    (DuckDB ``ensure_schema`` is not cheap). Tests that need pristine tables
    should TRUNCATE / DELETE inside the test itself.
    """
    previous = os.environ.get("BRAIN_DB_PATH")
    db = tmp_path_factory.mktemp("brain_duckdb") / "test.duckdb"
    os.environ["BRAIN_DB_PATH"] = str(db)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("BRAIN_DB_PATH", None)
        else:
            os.environ["BRAIN_DB_PATH"] = previous
