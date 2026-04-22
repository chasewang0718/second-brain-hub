"""Central defaults for local Ollama models (fast interactive vs heavy batch)."""

from __future__ import annotations

import os


def brain_fast_model() -> str:
    """Interactive paths: ``brain ask``, ``brain write``, Caps+D hot-path."""
    return os.getenv("BRAIN_FAST_MODEL", "qwen2.5:14b-instruct").strip() or "qwen2.5:14b-instruct"


def brain_heavy_model() -> str:
    """Batch / quality paths: people insights, entity extract, OCR structuring."""
    return os.getenv("BRAIN_HEAVY_MODEL", "qwen3:30b-a3b-instruct-2507").strip() or "qwen3:30b-a3b-instruct-2507"
