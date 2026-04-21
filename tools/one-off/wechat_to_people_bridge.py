"""Bridge WeChat exports into second-brain relationship notes (v2)."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ARTIFACTS_DIR = Path(r"C:\dev-projects\wechat-decoder\artifacts")
DEFAULT_BRAIN_ROOT = Path(r"D:\second-brain-content")
MAX_PREVIEW = 40
FOLLOWUP_PATTERNS = [
    r"(?:我|我们).*(?:会|将|准备|答应|承诺).*(?:发|给|做|安排|联系|回复)",
    r"(?:下周|明天|今晚|稍后).*(?:见|聊|联系|发|给|做)",
    r"(?:记得|需要|待办|todo|to-do)",
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_messages(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("chat json must be a list")
    return [x for x in data if isinstance(x, dict)]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def paraphrase_preview(msg: dict) -> str:
    content = clean_text(str(msg.get("content") or ""))
    if not content:
        msg_type = msg.get("msg_type")
        return f"[non-text:{msg_type}]"
    short = content[:MAX_PREVIEW]
    if len(content) > MAX_PREVIEW:
        short += "..."
    return short


def sender_slug(sender: str) -> str:
    sender = clean_text(sender).lower()
    sender = re.sub(r"[^a-z0-9_@\-]+", "-", sender).strip("-")
    return sender or "unknown"


def group_messages(messages: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        sender = str(msg.get("sender_display") or msg.get("sender") or "unknown")
        grouped[sender].append(msg)
    return grouped


def load_blacklist() -> list[str]:
    p = Path.home() / ".brain-exclude.txt"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            rows.append(s.lower())
    return rows


def path_is_blacklisted(path: Path, blacklist: list[str]) -> bool:
    low = str(path).lower()
    return any(pattern in low for pattern in blacklist)


def detect_pii(text: str) -> bool:
    # Optional presidio integration if installed.
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore

        analyzer = AnalyzerEngine()
        result = analyzer.analyze(text=text, entities=["PHONE_NUMBER", "EMAIL_ADDRESS"], language="en")
        if result:
            return True
    except Exception:
        pass
    fallback_patterns = [
        r"\b1[3-9]\d{9}\b",
        r"\b[\w.\-]+@[\w.\-]+\.\w+\b",
        r"\b\d{15,18}[0-9Xx]\b",
        r"\b(?:\d[ -]*?){13,19}\b",
    ]
    return any(re.search(p, text) for p in fallback_patterns)


def choose_sender_key(msg: dict) -> str:
    # Prefer durable sender id; fallback to display.
    sender = clean_text(str(msg.get("sender") or ""))
    display = clean_text(str(msg.get("sender_display") or ""))
    if sender and not sender.startswith("id:"):
        return sender
    return display or sender or "unknown"


def candidate_chat_files(artifacts_dir: Path) -> list[Path]:
    files = sorted(artifacts_dir.glob("chat_*.json"))
    out = []
    for f in files:
        name = f.name.lower()
        if "filehelper" in name or "file_transfer_assistant" in name:
            continue
        out.append(f)
    return out


def build_alias_map(messages: list[dict]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = defaultdict(set)
    for msg in messages:
        key = choose_sender_key(msg)
        sender = clean_text(str(msg.get("sender") or ""))
        display = clean_text(str(msg.get("sender_display") or ""))
        group_prefix = clean_text(str(msg.get("group_sender_prefix") or ""))
        for value in [sender, display, group_prefix]:
            if value:
                aliases[key].add(value)
    return aliases


def collect_followups(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        content = clean_text(str(msg.get("content") or ""))
        if not content:
            continue
        if any(re.search(p, content, flags=re.IGNORECASE) for p in FOLLOWUP_PATTERNS):
            out.append(
                {
                    "ts": msg.get("ts"),
                    "sender": choose_sender_key(msg),
                    "preview": content[:MAX_PREVIEW] + ("..." if len(content) > MAX_PREVIEW else ""),
                    "local_id": msg.get("local_id"),
                }
            )
    return out


def write_person_note(base_dir: Path, sender: str, messages: list[dict], source_files: set[str]) -> Path:
    slug = sender_slug(clean_text(sender))
    person_dir = base_dir / slug
    person_dir.mkdir(parents=True, exist_ok=True)
    out = base_dir / f"{slug}.md"
    interactions = person_dir / "interactions.md"
    lines: list[str] = []
    lines.append("---")
    lines.append(f"name: {clean_text(sender)}")
    lines.append(f"slug: {slug}")
    lines.append("relation: wechat-contact")
    lines.append(f"updated_at: {now_iso()}")
    lines.append("source: wechat-bridge")
    lines.append("---")
    lines.append("")
    lines.append(f"# {clean_text(sender)}")
    lines.append("")
    lines.append("## Quick Facts")
    lines.append("")
    lines.append("- relation: wechat-contact")
    lines.append(f"- interaction_count: {len(messages)}")
    lines.append(f"- last_contact: {max((str(m.get('ts') or '') for m in messages), default='')}")
    lines.append("")
    lines.append("## Interactions")
    lines.append("")
    lines.append(f"- details: [[06-people/wechat/{slug}/interactions]]")
    lines.append("")
    lines.append("## Source Pointer")
    lines.append("")
    for src in sorted(source_files):
        lines.append(f"- source_json: `{src}`")
    lines.append("- privacy: no raw quote over 40 chars")
    out.write_text("\n".join(lines), encoding="utf-8")

    ilines: list[str] = []
    ilines.append(f"# Interactions - {clean_text(sender)}")
    ilines.append("")
    for msg in sorted(messages, key=lambda x: str(x.get("ts") or "")):
        ts = str(msg.get("ts") or "")
        local_id = msg.get("local_id")
        preview = paraphrase_preview(msg)
        source_chat = msg.get("__source_file", "")
        ilines.append(f"- {ts} | local_id={local_id} | {preview} | source=`{source_chat}`")
    interactions.write_text("\n".join(ilines), encoding="utf-8")
    return out


def write_index(index_path: Path, created_files: list[Path]) -> None:
    lines = [
        "# WeChat Bridge Index",
        "",
        f"- generated_at: {now_iso()}",
        f"- people_count: {len(created_files)}",
        "",
    ]
    for f in sorted(created_files):
        lines.append(f"- [[06-people/wechat/{f.stem}]]")
    index_path.write_text("\n".join(lines), encoding="utf-8")


def write_aliases(path: Path, alias_map: dict[str, set[str]]) -> None:
    lines = ["# WeChat Aliases", "", f"- updated_at: {now_iso()}", ""]
    for key in sorted(alias_map):
        aliases = ", ".join(sorted(alias_map[key]))
        lines.append(f"- `{key}`: {aliases}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_followups(path: Path, followups: list[dict]) -> None:
    lines = ["# WeChat Followups", "", f"- updated_at: {now_iso()}", f"- count: {len(followups)}", ""]
    for item in sorted(followups, key=lambda x: str(x.get("ts") or "")):
        lines.append(
            f"- [ ] {item.get('ts')} | {item.get('sender')} | {item.get('preview')} | local_id={item.get('local_id')}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--chat-json", type=Path, default=None, help="optional single chat json")
    parser.add_argument("--brain-root", type=Path, default=DEFAULT_BRAIN_ROOT)
    args = parser.parse_args()
    blacklist = load_blacklist()
    if path_is_blacklisted(args.brain_root, blacklist):
        raise PermissionError(f"brain root is blacklisted by ~/.brain-exclude.txt: {args.brain_root}")

    people_dir = args.brain_root / "06-people" / "wechat"
    index_path = args.brain_root / "08-indexes" / "wechat-bridge-index.md"
    aliases_path = args.brain_root / "06-people" / "_aliases.md"
    followups_path = args.brain_root / "06-people" / "_followups.md"
    people_dir.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    aliases_path.parent.mkdir(parents=True, exist_ok=True)

    files = [args.chat_json] if args.chat_json else candidate_chat_files(args.artifacts_dir)
    files = [f for f in files if f and f.exists()]
    all_messages: list[dict] = []
    source_files: set[str] = set()
    skipped_pii = 0
    for f in files:
        msgs = read_messages(f)
        source_files.add(str(f))
        for msg in msgs:
            content = clean_text(str(msg.get("content") or ""))
            if content and detect_pii(content):
                skipped_pii += 1
                continue
            msg["__source_file"] = str(f)
            all_messages.append(msg)

    grouped = defaultdict(list)
    alias_map = build_alias_map(all_messages)
    for msg in all_messages:
        grouped[choose_sender_key(msg)].append(msg)
    followups = collect_followups(all_messages)
    created: list[Path] = []
    for sender, items in grouped.items():
        sender_sources = {str(x.get("__source_file", "")) for x in items}
        created.append(write_person_note(people_dir, sender, items, sender_sources))
    write_index(index_path, created)
    write_aliases(aliases_path, alias_map)
    write_followups(followups_path, followups)

    report = {
        "generated_at": now_iso(),
        "artifacts_dir": str(args.artifacts_dir),
        "source_chat_files": sorted(source_files),
        "brain_root": str(args.brain_root),
        "people_files": [str(p) for p in created],
        "index_file": str(index_path),
        "aliases_file": str(aliases_path),
        "followups_file": str(followups_path),
        "message_count": len(all_messages),
        "skipped_pii_count": skipped_pii,
        "blacklist_loaded_count": len(blacklist),
        "brain_root_blacklisted": path_is_blacklisted(args.brain_root, blacklist),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
