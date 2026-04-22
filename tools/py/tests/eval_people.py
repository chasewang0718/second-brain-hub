from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner
from brain_cli.main import app
from brain_memory.structured import execute, query


def _load_cases() -> list[dict[str, Any]]:
    cfg_path = Path(__file__).with_name("people_eval.yaml")
    payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases") or []
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("people_eval.yaml has no cases")
    return cases


def _load_optional_cases(file_name: str) -> list[dict[str, Any]]:
    path = Path(__file__).with_name(file_name)
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases") or []
    if not isinstance(cases, list):
        return []
    return [c for c in cases if isinstance(c, dict)]


def _run_json(args: list[str]) -> tuple[dict[str, Any] | list[Any], str]:
    runner = CliRunner()
    result = runner.invoke(app, args)
    if result.exit_code != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}")
    try:
        return json.loads(result.stdout), result.stdout
    except Exception as exc:
        raise AssertionError(f"json decode failed: {' '.join(args)}\n{result.stdout}") from exc


def _run_text(args: list[str]) -> str:
    runner = CliRunner()
    result = runner.invoke(app, args)
    if result.exit_code != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}")
    return result.stdout or ""


def _assert_case(case: dict[str, Any]) -> dict[str, Any]:
    cid = str(case.get("id") or "unknown")
    ctype = str(case.get("type") or "").strip().lower()
    inputs = case.get("input") or {}
    expect = case.get("expect") or {}

    if ctype == "who":
        payload, _ = _run_json(["who", str(inputs.get("name") or "")])
        if not isinstance(payload, list):
            raise AssertionError("who output is not list")
        if len(payload) < int(expect.get("min_results") or 0):
            raise AssertionError("who output has fewer rows than expected")
        max_results = expect.get("max_results")
        if max_results is not None and len(payload) > int(max_results):
            raise AssertionError("who output has more rows than expected")
        probes = [str(x).lower() for x in (expect.get("any_name_contains") or [])]
        if probes:
            names = [str(r.get("name") or "").lower() for r in payload]
            if not any(any(p in n for p in probes) for n in names):
                raise AssertionError("who output name check failed")
        required = [str(k) for k in (expect.get("require_keys") or [])]
        if required and payload:
            row = payload[0]
            missing = [k for k in required if k not in row]
            if missing:
                raise AssertionError(f"who output missing keys: {missing}")
        return {"id": cid, "type": ctype, "status": "pass", "rows": len(payload)}

    if ctype == "overdue":
        args = ["overdue", "--days", str(int(inputs.get("days") or 30))]
        channel = str(inputs.get("channel") or "").strip()
        if channel:
            args.extend(["--channel", channel])
        payload, _ = _run_json(args)
        if not isinstance(payload, list):
            raise AssertionError("overdue output is not list")
        if len(payload) < int(expect.get("min_results") or 0):
            raise AssertionError("overdue output has fewer rows than expected")
        required = [str(k) for k in (expect.get("require_keys") or [])]
        if required and payload:
            row = payload[0]
            missing = [k for k in required if k not in row]
            if missing:
                raise AssertionError(f"overdue output missing keys: {missing}")
        return {"id": cid, "type": ctype, "status": "pass", "rows": len(payload)}

    if ctype == "context":
        from brain_agents.people import context_for_meeting

        include_graph_hints = os.getenv("EVAL_PEOPLE_INCLUDE_GRAPH_HINTS", "0").strip() == "1"
        payload = context_for_meeting(
            name_or_alias=str(inputs.get("name") or ""),
            since_days=int(inputs.get("since_days") or 0) or None,
            limit=int(inputs.get("limit") or 5),
            include_graph_hints=include_graph_hints,
            auto_freshen_graph=include_graph_hints,
        )
        if not isinstance(payload, dict):
            raise AssertionError("context output is not dict")
        required = [str(k) for k in (expect.get("require_keys") or [])]
        missing = [k for k in required if k not in payload]
        if missing:
            raise AssertionError(f"context output missing keys: {missing}")
        if bool(expect.get("require_contact")) and not payload.get("contact"):
            raise AssertionError("context output has no contact")
        allowed_status = [str(x) for x in (expect.get("graph_hints_status_in") or [])] if include_graph_hints else []
        if allowed_status:
            hints = payload.get("graph_hints") or {}
            status = str(hints.get("status") or "")
            if status not in allowed_status:
                raise AssertionError(f"context graph_hints.status {status} not in {allowed_status}")
        min_shared = expect.get("min_shared_identifier")
        if min_shared is not None:
            hints = payload.get("graph_hints") or {}
            if str(hints.get("status") or "") != "ok":
                raise AssertionError("context graph_hints.status is not ok for shared_identifier assertion")
            shared_rows = hints.get("shared_identifier") or []
            if len(shared_rows) < int(min_shared):
                raise AssertionError("context output has fewer shared_identifier rows than expected")
        rows = len(payload.get("recent_interactions") or [])
        min_rows = expect.get("min_recent_interactions")
        if min_rows is not None and rows < int(min_rows):
            raise AssertionError("context output has fewer interactions than expected")
        return {"id": cid, "type": ctype, "status": "pass", "rows": rows}

    if ctype == "context_md":
        from brain_agents.people import context_for_meeting, context_for_meeting_markdown

        include_graph_hints = os.getenv("EVAL_PEOPLE_INCLUDE_GRAPH_HINTS", "0").strip() == "1"
        payload = context_for_meeting_markdown(
            context_for_meeting(
                name_or_alias=str(inputs.get("name") or ""),
                since_days=int(inputs.get("since_days") or 0) or None,
                limit=int(inputs.get("limit") or 5),
                include_graph_hints=include_graph_hints,
                auto_freshen_graph=include_graph_hints,
            )
        )
        contains_all = [str(x) for x in (expect.get("contains_all") or [])]
        missing = [s for s in contains_all if s not in payload]
        if missing:
            raise AssertionError(f"context md output missing snippets: {missing}")
        return {"id": cid, "type": ctype, "status": "pass", "chars": len(payload)}

    if ctype == "graph_shared_identifier":
        person_id = str(inputs.get("person_id") or "").strip()
        if not person_id:
            raise AssertionError("graph_shared_identifier requires person_id")
        from brain_agents.graph_build import build_graph
        from brain_agents.graph_query import shared_identifier

        build_graph()
        payload = shared_identifier(person_id, limit=int(expect.get("limit") or 20))
        rows = payload.get("results") or []
        min_rows = int(expect.get("min_rows") or 1)
        if len(rows) < min_rows:
            raise AssertionError("shared_identifier has fewer rows than expected")
        return {"id": cid, "type": ctype, "status": "pass", "rows": len(rows)}

    raise AssertionError(f"unsupported case type: {ctype}")


def _dynamic_real_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    recent_people = query(
        """
        SELECT primary_name
        FROM persons
        WHERE primary_name IS NOT NULL AND trim(primary_name) <> ''
        ORDER BY last_seen_utc DESC
        LIMIT 6
        """
    )
    for i, row in enumerate(recent_people, start=1):
        name = str(row.get("primary_name") or "").strip()
        if not name:
            continue
        cases.append(
            {
                "id": f"dyn_who_recent_{i}",
                "type": "who",
                "input": {"name": name},
                "expect": {"min_results": 1},
            }
        )

    interaction_people = query(
        """
        SELECT p.primary_name AS name, COUNT(*) AS cnt
        FROM interactions i
        JOIN persons p ON p.person_id = i.person_id
        WHERE p.primary_name IS NOT NULL AND trim(p.primary_name) <> ''
        GROUP BY 1
        ORDER BY cnt DESC
        LIMIT 3
        """
    )
    for i, row in enumerate(interaction_people, start=1):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        cases.append(
            {
                "id": f"dyn_context_interactions_{i}",
                "type": "context",
                "input": {"name": name, "since_days": 3650, "limit": 5},
                "expect": {
                    "require_contact": True,
                    "require_keys": ["contact", "recent_interactions", "graph_hints"],
                    "min_recent_interactions": 1,
                    "graph_hints_status_in": ["ok", "skipped"],
                },
            }
        )

    dup_names = query(
        """
        SELECT primary_name
        FROM persons
        WHERE primary_name IS NOT NULL AND trim(primary_name) <> ''
        GROUP BY 1
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC, primary_name
        LIMIT 2
        """
    )
    for i, row in enumerate(dup_names, start=1):
        name = str(row.get("primary_name") or "").strip()
        if not name:
            continue
        cases.append(
            {
                "id": f"dyn_who_duplicate_name_{i}",
                "type": "who",
                "input": {"name": name},
                "expect": {"min_results": 2},
            }
        )
    return cases


def _setup_alias_duplicate_fixture() -> dict[str, str]:
    a_id = "p_eval_alias_dup_a"
    b_id = "p_eval_alias_dup_b"
    c_id = "p_eval_alias_dup_c"
    shared_name = "Eval Duplicate Contact"
    alias_name = "Eval Alias Probe"
    canonical_name = "Eval Alias Canonical"

    execute("DELETE FROM interactions WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])
    execute("DELETE FROM person_identifiers WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])
    execute("DELETE FROM persons WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])
    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES
          (?, ?, '[]', '[]', CURRENT_TIMESTAMP),
          (?, ?, '[]', '[]', CURRENT_TIMESTAMP),
          (?, ?, ?, '[]', CURRENT_TIMESTAMP)
        """,
        [a_id, shared_name, b_id, shared_name, c_id, canonical_name, json.dumps([alias_name])],
    )
    return {"a_id": a_id, "b_id": b_id, "c_id": c_id, "shared_name": shared_name, "alias_name": alias_name}


def _teardown_alias_duplicate_fixture(ids: dict[str, str]) -> None:
    a_id = ids.get("a_id") or "p_eval_alias_dup_a"
    b_id = ids.get("b_id") or "p_eval_alias_dup_b"
    c_id = ids.get("c_id") or "p_eval_alias_dup_c"
    execute("DELETE FROM interactions WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])
    execute("DELETE FROM person_identifiers WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])
    execute("DELETE FROM persons WHERE person_id IN (?, ?, ?)", [a_id, b_id, c_id])


def _setup_graph_positive_fixture() -> dict[str, str]:
    a_id = "p_eval_graph_pos_a"
    b_id = "p_eval_graph_pos_b"
    shared_phone = "+8613800138000"

    # Cleanup first for idempotent reruns.
    execute("DELETE FROM interactions WHERE person_id IN (?, ?)", [a_id, b_id])
    execute("DELETE FROM person_identifiers WHERE person_id IN (?, ?)", [a_id, b_id])
    execute("DELETE FROM persons WHERE person_id IN (?, ?)", [a_id, b_id])

    execute(
        """
        INSERT INTO persons (person_id, primary_name, aliases_json, tags_json, last_seen_utc)
        VALUES (?, ?, '[]', '[]', CURRENT_TIMESTAMP), (?, ?, '[]', '[]', CURRENT_TIMESTAMP)
        """,
        [a_id, "GraphHint Alpha", b_id, "GraphHint Beta"],
    )
    execute(
        """
        INSERT INTO person_identifiers (person_id, kind, value_normalized, value_original, confidence, source_kind)
        VALUES (?, 'phone', ?, ?, 1.0, 'eval_fixture'),
               (?, 'phone', ?, ?, 1.0, 'eval_fixture')
        """,
        [a_id, shared_phone, shared_phone, b_id, shared_phone, shared_phone],
    )
    execute(
        """
        INSERT INTO interactions (id, person_id, ts_utc, channel, summary, source_path, detail_json, source_kind, source_id)
        VALUES
          (nextval('interactions_id_seq'), ?, CURRENT_TIMESTAMP, 'eval', 'graph hint seed alpha', 'eval://graph-positive', '{}', 'eval_fixture', 'graph_pos_a'),
          (nextval('interactions_id_seq'), ?, CURRENT_TIMESTAMP, 'eval', 'graph hint seed beta', 'eval://graph-positive', '{}', 'eval_fixture', 'graph_pos_b')
        """,
        [a_id, b_id],
    )
    return {"a_id": a_id, "b_id": b_id, "anchor_name": "GraphHint Alpha"}


def _teardown_graph_positive_fixture(ids: dict[str, str]) -> None:
    a_id = ids.get("a_id") or "p_eval_graph_pos_a"
    b_id = ids.get("b_id") or "p_eval_graph_pos_b"
    execute("DELETE FROM interactions WHERE person_id IN (?, ?)", [a_id, b_id])
    execute("DELETE FROM person_identifiers WHERE person_id IN (?, ?)", [a_id, b_id])
    execute("DELETE FROM persons WHERE person_id IN (?, ?)", [a_id, b_id])


def run_eval() -> dict[str, Any]:
    include_graph_positive = os.getenv("EVAL_PEOPLE_INCLUDE_GRAPH_POSITIVE", "0").strip() == "1"
    alias_dup_fixture = _setup_alias_duplicate_fixture()
    alias_dup_cases = [
        {
            "id": "fixture_who_alias_probe",
            "type": "who",
            "input": {"name": alias_dup_fixture["alias_name"]},
            "expect": {"min_results": 1, "any_name_contains": ["canonical"]},
        },
        {
            "id": "fixture_who_duplicate_contact",
            "type": "who",
            "input": {"name": alias_dup_fixture["shared_name"]},
            "expect": {"min_results": 2},
        },
    ]
    fixture_ids: dict[str, str] | None = None
    graph_positive_cases: list[dict[str, Any]] = []
    if include_graph_positive:
        fixture_ids = _setup_graph_positive_fixture()
        graph_positive_cases = [
            {
                "id": "graph_positive_shared_identifier",
                "type": "graph_shared_identifier",
                "input": {"person_id": fixture_ids["a_id"]},
                "expect": {"min_rows": 1, "limit": 10},
            }
        ]

    try:
        static_cases = _load_cases()
        golden_cases = _load_optional_cases("people_eval_golden.yaml")
        dynamic_cases = _dynamic_real_cases()
        cases = static_cases + golden_cases + alias_dup_cases + dynamic_cases + graph_positive_cases
        report: list[dict[str, Any]] = []
        passed = 0
        for case in cases:
            cid = str(case.get("id") or "unknown")
            ctype = str(case.get("type") or "unknown")
            try:
                item = _assert_case(case)
                passed += 1
            except Exception as exc:
                item = {"id": cid, "type": ctype, "status": "fail", "error": str(exc)}
            report.append(item)
    finally:
        _teardown_alias_duplicate_fixture(alias_dup_fixture)
        if fixture_ids is not None:
            _teardown_graph_positive_fixture(fixture_ids)
    return {
        "status": "ok" if passed == len(cases) else "partial",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "static_cases": len(static_cases),
        "golden_cases": len(golden_cases),
        "dynamic_cases_added": len(dynamic_cases),
        "graph_positive_cases": len(graph_positive_cases),
        "report": report,
    }


if __name__ == "__main__":
    print(json.dumps(run_eval(), ensure_ascii=False, indent=2))
