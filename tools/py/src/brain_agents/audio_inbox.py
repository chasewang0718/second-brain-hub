"""A3 audio inbox pipeline (faster-whisper optional).

Parallel to ``brain_agents.image_inbox`` / ``brain_agents.file_inbox``.
Given an audio path or the audio inbox directory, writes a Tier A
pointer card at
``D:\\second-brain-content\\03-projects\\inbox-auto-audio\\asset-<slug>.md``
with transcript text when ``faster_whisper`` is available. If the
library is not installed we still emit a pointer card with
``asr_status: pending`` and enqueue a cursor_queue task.

Design notes:
- faster-whisper import is lazy + guarded; zero hard dependency.
- Blacklist (``~/.brain-exclude.txt``) shared via ``file_inbox``.
- External audio files are copied into ``audio_inbox_dir`` before
  processing (same contract as PDF / image).
- Model selection: ``BRAIN_ASR_MODEL`` env var (default ``base``) and
  ``BRAIN_ASR_LANG`` (default autodetect).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_core.config import load_paths_config
from brain_agents.file_inbox import _is_excluded  # reuse shared blacklist


SUPPORTED_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".webm", ".aac", ".opus"}


def _paths() -> dict[str, str]:
    return load_paths_config()["paths"]


def _audio_inbox_dir() -> Path:
    return Path(_paths().get("audio_inbox_dir") or _paths()["pdf_inbox_dir"])


def _content_root() -> Path:
    return Path(_paths()["content_root"])


def _cursor_queue_dir() -> Path:
    return Path(_paths()["cursor_queue_dir"])


def _slug(raw: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "asset"


def _sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


@dataclass
class AudioIngestResult:
    source_path: str
    pointer_path: str
    status: str
    asr_status: str = "pending"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "pointer_path": self.pointer_path,
            "status": self.status,
            "asr_status": self.asr_status,
            "reason": self.reason,
        }


def _write_cursor_queue_task(audio_path: Path, reason: str) -> Path:
    queue_dir = _cursor_queue_dir()
    queue_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_path = queue_dir / f"audio-ingest-{stamp}-{_slug(audio_path.stem)}.md"
    task_path.write_text(
        "\n".join(
            [
                "---",
                "task: audio_ingest_fallback",
                f"created_utc: {datetime.now(UTC).isoformat()}",
                f"source_path: {audio_path}",
                f"reason: {reason}",
                "---",
                "",
                "# Audio Ingest Fallback",
                "",
                f"- Source: `{audio_path}`",
                f"- Reason: `{reason}`",
                "- Requested action: install `faster-whisper` (or run external ASR) then rerun `brain audio-inbox-ingest --path <file>`.",
            ]
        ),
        encoding="utf-8",
    )
    return task_path


def _pointer_card_path(audio_path: Path) -> Path:
    root = _content_root() / "03-projects" / "inbox-auto-audio"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"asset-{_slug(audio_path.stem)}.md"


def _try_asr(audio_path: Path) -> tuple[str, str, str, dict[str, Any]]:
    """Return (asr_status, excerpt, reason, meta).

    asr_status is one of: ``ok`` / ``pending`` / ``error``.
    When faster-whisper is not importable we return pending so the
    caller can still produce a pointer card.
    """
    meta: dict[str, Any] = {}
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on user env
        return "pending", "", f"faster_whisper_missing:{exc.__class__.__name__}", meta
    model_name = os.environ.get("BRAIN_ASR_MODEL", "base")
    lang = os.environ.get("BRAIN_ASR_LANG") or None
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), language=lang, vad_filter=True)
        lines: list[str] = []
        for seg in segments:
            txt = getattr(seg, "text", "").strip()
            if txt:
                lines.append(txt)
        meta["model"] = model_name
        meta["language"] = getattr(info, "language", lang or "auto")
        meta["duration"] = round(float(getattr(info, "duration", 0.0)), 2)
    except Exception as exc:  # pragma: no cover - runtime ASR failure
        return "error", "", f"faster_whisper_runtime:{exc}", meta
    excerpt = "\n".join(lines[:200])  # cap to protect pointer card size
    return ("ok" if lines else "pending"), excerpt, "" if lines else "empty_asr", meta


def _build_pointer_card(
    audio_path: Path,
    asr_status: str,
    excerpt: str,
    meta: dict[str, Any],
) -> str:
    stat = audio_path.stat()
    body: list[str] = [
        "---",
        f"title: {audio_path.stem}",
        "asset_type: audio",
        f"asset_path: {audio_path}",
        f"asset_size: {_human_size(stat.st_size)}",
        f"asset_sha256: {_sha256_prefix(audio_path)}",
        f"asr_status: {asr_status}",
    ]
    if meta.get("model"):
        body.append(f"asr_model: {meta['model']}")
    if meta.get("language"):
        body.append(f"asr_language: {meta['language']}")
    if meta.get("duration") is not None:
        body.append(f"asr_duration_seconds: {meta['duration']}")
    body.extend([
        "source_original_path: unknown",
        f"created: {datetime.now(UTC).date().isoformat()}",
        "tags: [asset, audio, pointer-card, auto-ingest]",
        "---",
        "",
        f"# {audio_path.stem}",
        "",
        "## 语音转写正文",
    ])
    if excerpt:
        body.append("")
        body.append("```text")
        body.append(excerpt)
        body.append("```")
    else:
        body.append("- [TODO] ASR 尚未产生文本 (faster-whisper 未安装或空结果)。")
    body.extend([
        "",
        "## 关键词",
        "- audio",
        "- inbox",
        "",
        "## 我的备注",
        "",
    ])
    return "\n".join(body)


def _copy_into_inbox(audio_path: Path) -> Path:
    inbox = _audio_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    try:
        resolved_src = audio_path.resolve()
        resolved_inbox = inbox.resolve()
    except OSError:
        resolved_src = audio_path
        resolved_inbox = inbox
    try:
        inside = str(resolved_src).lower().startswith(
            str(resolved_inbox).lower() + os.sep.lower()
        )
    except Exception:
        inside = False
    if inside:
        return resolved_src
    target = inbox / audio_path.name
    if target.exists():
        stem = audio_path.stem
        suffix = audio_path.suffix
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = inbox / f"{stem}-{stamp}{suffix}"
    shutil.copy2(audio_path, target)
    return target


def ingest_audio(audio_path: Path) -> dict[str, Any]:
    try:
        if not audio_path.exists():
            return AudioIngestResult(str(audio_path), "", "skipped", "pending", "missing").to_dict()
        if audio_path.suffix.lower() not in SUPPORTED_EXT:
            return AudioIngestResult(
                str(audio_path), "", "skipped", "pending", f"unsupported_ext:{audio_path.suffix.lower()}"
            ).to_dict()
        pattern = _is_excluded(audio_path)
        if pattern:
            return AudioIngestResult(
                str(audio_path), "", "skipped", "pending", f"blacklist:{pattern}"
            ).to_dict()
        asr_status, excerpt, asr_reason, meta = _try_asr(audio_path)
        pointer = _pointer_card_path(audio_path)
        pointer.write_text(
            _build_pointer_card(audio_path, asr_status, excerpt, meta),
            encoding="utf-8",
        )
        task_path = ""
        if asr_status != "ok":
            task_path = str(_write_cursor_queue_task(audio_path, asr_reason or asr_status))
        out = AudioIngestResult(str(audio_path), str(pointer), "ok", asr_status, asr_reason).to_dict()
        if task_path:
            out["cursor_queue_task"] = task_path
        if meta:
            out["asr_meta"] = meta
        return out
    except Exception as exc:
        task_path = _write_cursor_queue_task(audio_path, str(exc))
        return AudioIngestResult(
            str(audio_path), str(task_path), "queued", "error", str(exc)
        ).to_dict()


def ingest_audio_paths(paths: list[str | Path], copy_into_inbox: bool = True) -> list[dict[str, Any]]:
    """Ingest an explicit list of audio paths (mirrors ingest_image_paths)."""
    results: list[dict[str, Any]] = []
    for raw in paths:
        try:
            src = Path(raw).expanduser()
        except Exception as exc:
            results.append(
                AudioIngestResult(str(raw), "", "skipped", "pending", f"bad_path:{exc}").to_dict()
            )
            continue
        if src.suffix.lower() not in SUPPORTED_EXT:
            results.append(
                AudioIngestResult(str(src), "", "skipped", "pending", f"unsupported_ext:{src.suffix.lower()}").to_dict()
            )
            continue
        if not src.exists():
            results.append(
                AudioIngestResult(str(src), "", "skipped", "pending", "missing").to_dict()
            )
            continue
        pattern = _is_excluded(src)
        if pattern:
            results.append(
                AudioIngestResult(str(src), "", "skipped", "pending", f"blacklist:{pattern}").to_dict()
            )
            continue
        try:
            target = _copy_into_inbox(src) if copy_into_inbox else src
        except Exception as exc:
            results.append(
                AudioIngestResult(str(src), "", "skipped", "pending", f"copy_failed:{exc}").to_dict()
            )
            continue
        result = ingest_audio(target)
        result["source_path"] = str(src)
        result["inbox_path"] = str(target)
        results.append(result)
    return results


def ingest_audio_inbox(limit: int = 1) -> list[dict[str, Any]]:
    inbox = _audio_inbox_dir()
    if not inbox.exists():
        return []
    files = sorted(
        p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )
    if limit > 0:
        files = files[:limit]
    return [ingest_audio(path) for path in files]
