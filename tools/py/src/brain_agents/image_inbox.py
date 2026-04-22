"""A3 image inbox pipeline (paddleocr optional).

Parallel to ``brain_agents.file_inbox`` (PDF). Given an image path or the
image inbox directory, writes a Tier A pointer card to
``D:\\second-brain-content\\03-projects\\inbox-auto-image\\asset-<slug>.md``
with OCR text when paddleocr is available. If paddleocr is not installed
we still emit a pointer card with ``ocr_status: pending`` and enqueue a
cursor_queue task so the user can fill it in later.

Design notes:
- paddleocr import is lazy + guarded: the hub must not hard-depend on it.
- Blacklist (``~/.brain-exclude.txt``) is shared with PDF via file_inbox.
- External images are copied into ``image_inbox_dir`` before processing
  so the original tree stays untouched (same contract as PDFs).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from brain_agents.file_inbox import _is_excluded  # reuse shared blacklist
from brain_core.config import load_paths_config


SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _paths() -> dict[str, str]:
    return load_paths_config()["paths"]


def _image_inbox_dir() -> Path:
    return Path(_paths().get("image_inbox_dir") or _paths()["pdf_inbox_dir"])


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
class ImageIngestResult:
    source_path: str
    pointer_path: str
    status: str
    ocr_status: str = "pending"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "pointer_path": self.pointer_path,
            "status": self.status,
            "ocr_status": self.ocr_status,
            "reason": self.reason,
        }


def _write_cursor_queue_task(img_path: Path, reason: str) -> Path:
    queue_dir = _cursor_queue_dir()
    queue_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    task_path = queue_dir / f"image-ingest-{stamp}-{_slug(img_path.stem)}.md"
    task_path.write_text(
        "\n".join(
            [
                "---",
                "task: image_ingest_fallback",
                f"created_utc: {datetime.now(UTC).isoformat()}",
                f"source_path: {img_path}",
                f"reason: {reason}",
                "---",
                "",
                "# Image Ingest Fallback",
                "",
                f"- Source: `{img_path}`",
                f"- Reason: `{reason}`",
                "- Requested action: run OCR manually or install `paddleocr`, then rerun `brain image-inbox-ingest --path <file>`.",
            ]
        ),
        encoding="utf-8",
    )
    return task_path


def _pointer_card_path(img_path: Path) -> Path:
    root = _content_root() / "03-projects" / "inbox-auto-image"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"asset-{_slug(img_path.stem)}.md"


def _try_ocr(img_path: Path) -> tuple[str, str, str]:
    """Return (ocr_status, excerpt, reason).

    ocr_status is one of: ``ok`` / ``pending`` / ``error``.
    When paddleocr is not importable we return pending so the caller can
    still produce a pointer card.
    """
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on user env
        return "pending", "", f"paddleocr_missing:{exc.__class__.__name__}"
    try:
        reader = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        raw = reader.ocr(str(img_path), cls=True)
    except Exception as exc:  # pragma: no cover - runtime OCR failure
        return "error", "", f"paddleocr_runtime:{exc}"
    lines: list[str] = []
    for page in raw or []:
        for item in page or []:
            try:
                text = item[1][0]
            except Exception:
                continue
            if text:
                lines.append(str(text))
    excerpt = "\n".join(lines[:50])
    return ("ok" if lines else "pending"), excerpt, "" if lines else "empty_ocr"


def _structure_ocr_with_llm(excerpt: str) -> tuple[str, str]:
    """Heavy-model JSON extraction from OCR text. Returns (json_text, error_or_empty)."""
    try:
        from ollama import Client

        from brain_core.ollama_models import brain_heavy_model
    except Exception as exc:
        return "", f"import:{exc}"

    snippet = excerpt.strip()
    if len(snippet) < 8:
        return "", "excerpt_too_short"
    host = os.getenv("OLLAMA_HOST", "").strip()
    cli = Client(host=host) if host else Client()
    model = brain_heavy_model()
    prompt = (
        "From the OCR text below, reply with ONE JSON object only (no markdown fence). Keys:\n"
        '- "people": array of person names mentioned\n'
        '- "event_time": ISO-8601 datetime string or empty string if unknown\n'
        '- "event": short natural-language description of what happened\n'
        '- "objects": short phrase for main physical/digital object(s)\n'
        "Match the OCR language.\n\nOCR:\n"
        f"{snippet[:6000]}"
    )
    try:
        out = cli.generate(model=model, prompt=prompt)
        if hasattr(out, "response"):
            raw = str(getattr(out, "response") or "").strip()
        elif isinstance(out, dict):
            raw = str(out.get("response", "")).strip()
        else:
            raw = str(out).strip()
        raw = re.sub(r"^```[a-zA-Z0-9]*\n?", "", raw).strip()
        raw = re.sub(r"\n?```\s*$", "", raw).strip()
        json.loads(raw)
        return raw, ""
    except Exception as exc:
        return "", str(exc)


def _enqueue_ocr_hard_queue(img_path: Path, *, ocr_status: str, reason: str) -> dict[str, Any] | None:
    try:
        from brain_agents.cloud_queue import enqueue

        return enqueue(
            "ocr-hard",
            {"path": str(img_path), "ocr_status": ocr_status, "reason": reason[:2000]},
        )
    except Exception:
        return None


def _build_pointer_card(
    img_path: Path,
    ocr_status: str,
    excerpt: str,
    *,
    structured_status: str = "",
    structured_json: str = "",
) -> str:
    stat = img_path.stat()
    body: list[str] = [
        "---",
        f"title: {img_path.stem}",
        "asset_type: image",
        f"asset_path: {img_path}",
        f"asset_size: {_human_size(stat.st_size)}",
        f"asset_sha256: {_sha256_prefix(img_path)}",
        f"ocr_status: {ocr_status}",
        f"structured_status: {structured_status or 'skipped'}",
        "source_original_path: unknown",
        f"created: {datetime.now(UTC).date().isoformat()}",
        "tags: [asset, image, pointer-card, auto-ingest]",
        "---",
        "",
        f"# {img_path.stem}",
        "",
        "## OCR 正文",
    ]
    if excerpt:
        body.append("")
        body.append("```text")
        body.append(excerpt)
        body.append("```")
    else:
        body.append("- [TODO] OCR 尚未产生文本 (paddleocr 未安装或空结果)。")
    if structured_json.strip():
        body.extend(
            [
                "",
                "## LLM 结构化 (heavy)",
                "",
                "```json",
                structured_json.strip(),
                "```",
            ]
        )
    body.extend([
        "",
        "## 关键词",
        "- image",
        "- inbox",
        "",
        "## 我的备注",
        "",
    ])
    return "\n".join(body)


def _copy_into_inbox(img_path: Path) -> Path:
    inbox = _image_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    try:
        resolved_src = img_path.resolve()
        resolved_inbox = inbox.resolve()
    except OSError:
        resolved_src = img_path
        resolved_inbox = inbox
    try:
        inside = str(resolved_src).lower().startswith(
            str(resolved_inbox).lower() + os.sep.lower()
        )
    except Exception:
        inside = False
    if inside:
        return resolved_src
    target = inbox / img_path.name
    if target.exists():
        stem = img_path.stem
        suffix = img_path.suffix
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = inbox / f"{stem}-{stamp}{suffix}"
    shutil.copy2(img_path, target)
    return target


def ingest_image(img_path: Path) -> dict[str, Any]:
    try:
        if not img_path.exists():
            return ImageIngestResult(str(img_path), "", "skipped", "pending", "missing").to_dict()
        if img_path.suffix.lower() not in SUPPORTED_EXT:
            return ImageIngestResult(
                str(img_path), "", "skipped", "pending", f"unsupported_ext:{img_path.suffix.lower()}"
            ).to_dict()
        pattern = _is_excluded(img_path)
        if pattern:
            return ImageIngestResult(
                str(img_path), "", "skipped", "pending", f"blacklist:{pattern}"
            ).to_dict()
        ocr_status, excerpt, ocr_reason = _try_ocr(img_path)
        structured_status = ""
        structured_json = ""
        if (
            ocr_status == "ok"
            and excerpt.strip()
            and os.getenv("BRAIN_IMAGE_STRUCTURE", "0").strip() == "1"
        ):
            structured_json, serr = _structure_ocr_with_llm(excerpt)
            structured_status = "ok" if structured_json.strip() else f"error:{serr}"
        pointer = _pointer_card_path(img_path)
        pointer.write_text(
            _build_pointer_card(
                img_path,
                ocr_status,
                excerpt,
                structured_status=structured_status,
                structured_json=structured_json,
            ),
            encoding="utf-8",
        )
        task_path = ""
        if ocr_status != "ok":
            task_path = str(_write_cursor_queue_task(img_path, ocr_reason or ocr_status))
        cq = None
        if ocr_status in ("pending", "error"):
            cq = _enqueue_ocr_hard_queue(img_path, ocr_status=ocr_status, reason=ocr_reason or ocr_status)
        result = ImageIngestResult(str(img_path), str(pointer), "ok", ocr_status, ocr_reason)
        out = result.to_dict()
        if task_path:
            out["cursor_queue_task"] = task_path
        if cq:
            out["cloud_queue"] = cq
        return out
    except Exception as exc:
        task_path = _write_cursor_queue_task(img_path, str(exc))
        return ImageIngestResult(
            str(img_path), str(task_path), "queued", "error", str(exc)
        ).to_dict()


def ingest_image_paths(paths: list[str | Path], copy_into_inbox: bool = True) -> list[dict[str, Any]]:
    """Ingest an explicit list of image paths (mirrors ingest_pdf_paths)."""
    results: list[dict[str, Any]] = []
    for raw in paths:
        try:
            src = Path(raw).expanduser()
        except Exception as exc:
            results.append(
                ImageIngestResult(str(raw), "", "skipped", "pending", f"bad_path:{exc}").to_dict()
            )
            continue
        if src.suffix.lower() not in SUPPORTED_EXT:
            results.append(
                ImageIngestResult(str(src), "", "skipped", "pending", f"unsupported_ext:{src.suffix.lower()}").to_dict()
            )
            continue
        if not src.exists():
            results.append(
                ImageIngestResult(str(src), "", "skipped", "pending", "missing").to_dict()
            )
            continue
        pattern = _is_excluded(src)
        if pattern:
            results.append(
                ImageIngestResult(str(src), "", "skipped", "pending", f"blacklist:{pattern}").to_dict()
            )
            continue
        try:
            target = _copy_into_inbox(src) if copy_into_inbox else src
        except Exception as exc:
            results.append(
                ImageIngestResult(str(src), "", "skipped", "pending", f"copy_failed:{exc}").to_dict()
            )
            continue
        result = ingest_image(target)
        result["source_path"] = str(src)
        result["inbox_path"] = str(target)
        results.append(result)
    return results


def ingest_image_inbox(limit: int = 1) -> list[dict[str, Any]]:
    inbox = _image_inbox_dir()
    if not inbox.exists():
        return []
    imgs = sorted(
        p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )
    if limit > 0:
        imgs = imgs[:limit]
    return [ingest_image(path) for path in imgs]
