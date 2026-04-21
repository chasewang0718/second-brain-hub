"""LanceDB vector store backed by Ollama embeddings."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
from time import perf_counter
from typing import Any

import lancedb
from ollama import Client, ResponseError

from brain_core.config import load_paths_config

EMBED_MODEL = "nomic-embed-text"
TABLE_NAME = "content_vectors"
MAX_EMBED_CHARS = 1500


def _content_root() -> Path:
    override = os.getenv("BRAIN_CONTENT_ROOT_OVERRIDE", "").strip()
    if override:
        return Path(override)
    return Path(load_paths_config()["paths"]["content_root"])


def _vector_db_dir() -> Path:
    override = os.getenv("BRAIN_VECTOR_DB_OVERRIDE", "").strip()
    if override:
        path = Path(override)
    else:
        logs_dir = Path(load_paths_config()["paths"]["telemetry_logs_dir"])
        path = logs_dir.parent / "vector-index"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client() -> Client:
    host = os.getenv("OLLAMA_HOST", "").strip()
    return Client(host=host) if host else Client()


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    vectors: list[list[float]] = []
    for raw in texts:
        candidate = raw[:MAX_EMBED_CHARS]
        got: list[float] | None = None
        for cap in (1500, 1000, 700, 400, 250):
            snippet = candidate[:cap]
            try:
                response = client.embed(model=EMBED_MODEL, input=snippet)
                got = list(map(float, response["embeddings"][0]))
                break
            except ResponseError:
                continue
            except Exception:
                # Compatibility fallback for older ollama-python versions.
                try:
                    old = client.embeddings(model=EMBED_MODEL, prompt=snippet)
                    got = list(map(float, old["embedding"]))
                    break
                except Exception:
                    continue
        if got is None:
            raise RuntimeError("Unable to embed text snippet within model context limits")
        vectors.append(got)
    return vectors


def _doc_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()


def _scan_markdown_files(limit: int = 0) -> list[Path]:
    files = sorted(_content_root().rglob("*.md"))
    if limit > 0:
        return files[:limit]
    return files


def _keyword_search(query: str, limit: int) -> list[dict[str, Any]]:
    raw = query.strip()
    if not raw:
        return []
    terms = _keyword_terms(raw)
    if not terms:
        return []
    scored: dict[Path, int] = {}
    for term in terms[:6]:
        for path in _rg_files_with_match(term):
            scored[path] = scored.get(path, 0) + 1
    if not scored:
        return []
    ranked = sorted(scored.items(), key=lambda item: (-item[1], str(item[0])))
    matches: list[dict[str, Any]] = []
    for path, score in ranked[:limit]:
        text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
        preview = text.strip().replace("\r", " ").replace("\n", " ")
        matches.append(
            {
                "path": str(path),
                "title": path.stem,
                "preview": preview[:220],
                "score": float(-score),
                "method": "keyword",
            }
        )
    return matches


def _keyword_terms(query: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", query.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) >= 4:
            # For Chinese queries without spaces, add bi-grams to improve recall.
            terms.extend(token[i : i + 2] for i in range(len(token) - 1))
        terms.append(token)
    # De-dup while preserving order.
    uniq: list[str] = []
    for item in terms:
        if item and item not in uniq:
            uniq.append(item)
    return uniq


def _rg_files_with_match(term: str) -> list[Path]:
    root = _content_root()
    try:
        proc = subprocess.run(
            ["rg", "-F", "-l", "--glob", "*.md", term, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode not in (0, 1):
        return []
    out: list[Path] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            out.append(Path(line))
    return out


def _build_row(path: Path, vector: list[float]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    preview = text.strip().replace("\r", " ").replace("\n", " ")
    return {
        "id": _doc_id(path),
        "path": str(path),
        "title": path.stem,
        "mtime_ns": path.stat().st_mtime_ns,
        "chars": len(text),
        "preview": preview[:220],
        "vector": vector,
    }


def rebuild_index(limit: int = 0) -> dict[str, Any]:
    start = perf_counter()
    files = _scan_markdown_files(limit=limit)
    texts = [f.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff") for f in files]
    vectors = _embed_texts(texts)
    rows = [_build_row(path=path, vector=vector) for path, vector in zip(files, vectors, strict=False)]

    db = lancedb.connect(str(_vector_db_dir()))
    if rows:
        db.create_table(TABLE_NAME, data=rows, mode="overwrite")
    elapsed_ms = int((perf_counter() - start) * 1000)
    return {"indexed": len(rows), "elapsed_ms": elapsed_ms, "table": TABLE_NAME}


def upsert_markdown(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.exists() or path.suffix.lower() != ".md":
        return {"ok": False, "reason": "not_markdown_or_missing", "path": path_str}
    text = path.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")
    vector = _embed_texts([text])[0]
    row = _build_row(path=path, vector=vector)

    db = lancedb.connect(str(_vector_db_dir()))
    if TABLE_NAME not in db.table_names():
        db.create_table(TABLE_NAME, data=[row], mode="overwrite")
    else:
        table = db.open_table(TABLE_NAME)
        table.delete(f"id = '{row['id']}'")
        table.add([row])
    return {"ok": True, "path": path_str, "id": row["id"]}


def delete_markdown(path_str: str) -> dict[str, Any]:
    db = lancedb.connect(str(_vector_db_dir()))
    if TABLE_NAME not in db.table_names():
        return {"ok": True, "deleted": 0, "path": path_str}
    row_id = _doc_id(Path(path_str))
    table = db.open_table(TABLE_NAME)
    table.delete(f"id = '{row_id}'")
    return {"ok": True, "deleted": 1, "path": path_str}


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    keyword_hits = _keyword_search(query=query, limit=limit)
    if keyword_hits:
        return keyword_hits
    db = lancedb.connect(str(_vector_db_dir()))
    if TABLE_NAME not in db.table_names():
        return []
    query_vector = _embed_texts([query])[0]
    table = db.open_table(TABLE_NAME)
    rows = table.search(query_vector).limit(limit).to_list()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "path": row.get("path", ""),
                "title": row.get("title", ""),
                "preview": row.get("preview", ""),
                "score": float(row.get("_distance", 0.0)),
                "method": "vector",
            }
        )
    return out

