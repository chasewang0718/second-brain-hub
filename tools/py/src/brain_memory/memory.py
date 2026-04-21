"""Unified memory facade for vectors + graph + structured."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brain_agents.ask import ask as ask_engine
from brain_memory.graph import ensure_schema as ensure_graph_schema
from brain_memory.graph import query as graph_query
from brain_memory.structured import ensure_schema as ensure_structured_schema
from brain_memory.structured import query as structured_query
from brain_memory.vectors import search as vector_search


@dataclass
class Memory:
    def bootstrap(self) -> dict[str, Any]:
        ensure_structured_schema()
        graph_state = ensure_graph_schema()
        return {"structured": "ok", "graph": graph_state.get("status", "ok")}

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return vector_search(query=query, limit=limit)

    def query_graph(self, cypher: str) -> list[dict[str, Any]]:
        return graph_query(cypher)

    def query_structured(self, sql: str) -> list[dict[str, Any]]:
        return structured_query(sql)

    def ask(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return ask_engine(query=query, limit=limit)

