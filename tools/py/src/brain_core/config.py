"""Load v5 path and threshold config from hub repo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    # src/brain_core/config.py -> tools/py/src/brain_core -> repo root
    return Path(__file__).resolve().parents[4]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be mapping: {path}")
    return data


def load_paths_config() -> dict[str, Any]:
    return _read_yaml(_repo_root() / "config" / "paths.yaml")


def load_thresholds_config() -> dict[str, Any]:
    return _read_yaml(_repo_root() / "config" / "thresholds.yaml")


def load_runtime_config() -> dict[str, Any]:
    return {
        "paths": load_paths_config(),
        "thresholds": load_thresholds_config(),
    }

