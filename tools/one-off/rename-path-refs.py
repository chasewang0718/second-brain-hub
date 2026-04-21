"""One-off script: fix dead path references after v5 rename.

Scans a tree recursively for text files and replaces:
  D:\brain\          -> D:\second-brain-content\
  D:\brain-assets\   -> D:\second-brain-assets\

Also handles forward-slash variants. Idempotent.

Usage:
  python rename-path-refs.py [ROOT]
  default ROOT = D:\\second-brain-content
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\second-brain-content")

# Patterns: (old, new). Order matters - do brain-assets BEFORE brain to avoid partial match.
PATTERNS = [
    # Backslash variants
    (r"D:\brain-assets\\", r"D:\second-brain-assets\\"),
    (r"D:\brain-assets\ ", r"D:\second-brain-assets\ "),  # trailing space
    (r"D:\\brain-assets\\", r"D:\\second-brain-assets\\"),
    (r"D:\brain-assets/", r"D:\second-brain-assets/"),
    # Bare (no trailing sep) but only when followed by sep-like char; handled by above mostly
    # Brain (content):
    (r"D:\brain\\", r"D:\second-brain-content\\"),
    (r"D:\\brain\\", r"D:\\second-brain-content\\"),
    (r"D:\brain/", r"D:\second-brain-content/"),
]

# Simpler: do literal string replace for two tokens, most robust
def fix(content: str) -> tuple[str, int]:
    changes = 0
    new = content
    # Replace more specific first
    # Specific (with trailing sep) MUST go first to avoid partial double-replaces.
    # Safety: D:\brain-assets is NOT a substring of D:\second-brain-assets (D:\s... vs D:\b...).
    for old, new_str in [
        ("D:\\brain-assets\\", "D:\\second-brain-assets\\"),
        ("D:/brain-assets/", "D:/second-brain-assets/"),
        ("D:\\brain\\", "D:\\second-brain-content\\"),
        ("D:/brain/", "D:/second-brain-content/"),
        ("D:\\brain-assets", "D:\\second-brain-assets"),
        ("D:/brain-assets", "D:/second-brain-assets"),
        ("D:\\brain", "D:\\second-brain-content"),
        ("D:/brain", "D:/second-brain-content"),
    ]:
        count = new.count(old)
        if count:
            new = new.replace(old, new_str)
            changes += count
    return new, changes


def main():
    files_changed = 0
    total_replaces = 0
    # Only .md and .yaml / .yml
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".md", ".yaml", ".yml", ".txt", ".ps1", ".psm1", ".json", ".ahk"}:
            continue
        # Skip this script itself (self-contains the literals for replacement!)
        if "rename-path-refs.py" in str(p):
            continue
        # Skip .git
        if ".git" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new_text, n = fix(text)
        if n:
            p.write_text(new_text, encoding="utf-8")
            files_changed += 1
            total_replaces += n
            print(f"  [{n}] {p.relative_to(ROOT)}")
    print(f"\nDone. {files_changed} files changed, {total_replaces} total replacements.")


if __name__ == "__main__":
    sys.exit(main())
