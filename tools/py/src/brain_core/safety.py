"""Git safety net helpers for agent auto-commit and restore."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
import json
import os
from pathlib import Path
from typing import Any

from git import Repo

from brain_core.config import load_paths_config
from brain_core.telemetry import append_event

AGENT_PREFIX = "[agent:"


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")


def _safe_slug(raw: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "agent"


def resolve_content_repo() -> Repo:
    override = os.getenv("BRAIN_CONTENT_ROOT_OVERRIDE", "").strip()
    content_root = Path(override) if override else Path(load_paths_config()["paths"]["content_root"])
    if not content_root.exists():
        raise FileNotFoundError(f"content_root does not exist: {content_root}")
    return Repo(str(content_root))


def format_agent_commit_message(agent: str, summary: str, actions: list[str] | None = None) -> str:
    title = f"[agent:{_safe_slug(agent)}] {summary.strip()}"
    detail_lines = [f"- {item.strip()}" for item in (actions or []) if item.strip()]
    if not detail_lines:
        return title
    return title + "\n\n" + "\n".join(detail_lines)


@dataclass
class BackupBrancher:
    """Create a movable backup branch pointer before destructive actions."""

    repo: Repo
    agent: str

    def create(self) -> str:
        branch_name = f"backup/{_safe_slug(self.agent)}/{_utc_stamp()}"
        self.repo.git.branch(branch_name, self.repo.head.commit.hexsha)
        return branch_name


@dataclass
class AutoCommitter:
    """Context manager that auto-commits staged/unstaged changes."""

    agent: str
    summary: str
    actions: list[str] = field(default_factory=list)
    repo: Repo = field(default_factory=resolve_content_repo)
    backup_branch: str = ""
    before_head: str = ""
    commit_hexsha: str = ""

    def __enter__(self) -> "AutoCommitter":
        if self.repo.is_dirty(untracked_files=True):
            raise RuntimeError(
                "Content repo has pre-existing dirty changes; auto-commit is blocked to avoid mixed commits"
            )
        self.before_head = self.repo.head.commit.hexsha
        self.backup_branch = BackupBrancher(repo=self.repo, agent=self.agent).create()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is not None:
            return False
        self.repo.git.add(A=True)
        if self.repo.is_dirty(untracked_files=True):
            msg = format_agent_commit_message(self.agent, self.summary, self.actions)
            self.repo.index.commit(msg)
            self.commit_hexsha = self.repo.head.commit.hexsha
            append_event(
                source="safety",
                event="auto_commit",
                detail_json=json.dumps(
                    {
                        "agent": _safe_slug(self.agent),
                        "commit": self.commit_hexsha,
                        "backup_branch": self.backup_branch,
                    },
                    ensure_ascii=False,
                ),
            )
        return False


def list_history(limit: int = 20, agent: str = "") -> list[dict[str, Any]]:
    repo = resolve_content_repo()
    rows: list[dict[str, Any]] = []
    agent_prefix = f"[agent:{_safe_slug(agent)}]" if agent else ""
    for commit in repo.iter_commits("HEAD", max_count=max(limit * 5, limit)):
        subject = commit.message.splitlines()[0] if commit.message else ""
        if agent_prefix and not subject.startswith(agent_prefix):
            continue
        rows.append(
            {
                "hexsha": commit.hexsha,
                "short": commit.hexsha[:8],
                "summary": subject,
                "authored_utc": datetime.fromtimestamp(commit.committed_date, UTC).isoformat(),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def find_last_clean_commit() -> str:
    repo = resolve_content_repo()
    for commit in repo.iter_commits("HEAD"):
        subject = commit.message.splitlines()[0] if commit.message else ""
        if not subject.startswith(AGENT_PREFIX):
            return commit.hexsha
    raise RuntimeError("No clean commit found in history")


def _tag_pre_restore(repo: Repo) -> str:
    tag_name = f"pre-restore/{_utc_stamp()}"
    repo.create_tag(tag_name, message="Automatic snapshot before restore")
    return tag_name


def restore_to(commit: str) -> dict[str, str]:
    repo = resolve_content_repo()
    if repo.is_dirty(untracked_files=True):
        raise RuntimeError("Content repo is dirty; commit/stash first before restore")
    snapshot_tag = _tag_pre_restore(repo)
    repo.git.reset("--hard", commit)
    after = repo.head.commit.hexsha
    append_event(
        source="safety",
        event="restore",
        detail_json=json.dumps(
            {"mode": "to", "target": commit, "result": after, "snapshot": snapshot_tag},
            ensure_ascii=False,
        ),
    )
    return {"target": commit, "head": after, "snapshot_tag": snapshot_tag}


def restore_last_clean() -> dict[str, str]:
    clean = find_last_clean_commit()
    return restore_to(clean)


def restore_agent(agent: str) -> dict[str, str]:
    repo = resolve_content_repo()
    target_prefix = f"[agent:{_safe_slug(agent)}]"
    head = repo.head.commit
    head_subject = head.message.splitlines()[0] if head.message else ""
    if not head_subject.startswith(target_prefix):
        raise RuntimeError("HEAD is not an agent commit for this agent")

    cursor = head
    while True:
        parents = cursor.parents
        if not parents:
            raise RuntimeError("Cannot restore past root commit")
        parent = parents[0]
        parent_subject = parent.message.splitlines()[0] if parent.message else ""
        if not parent_subject.startswith(target_prefix):
            return restore_to(parent.hexsha)
        cursor = parent


def safety_status() -> dict[str, Any]:
    repo = resolve_content_repo()
    head = repo.head.commit
    subject = head.message.splitlines()[0] if head.message else ""
    return {
        "repo": str(Path(repo.working_tree_dir or "")),
        "head": head.hexsha,
        "head_summary": subject,
        "dirty": repo.is_dirty(untracked_files=True),
        "untracked": len(repo.untracked_files),
    }
