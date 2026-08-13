#!/usr/bin/env python3
"""Tag and push a lasers release from pyproject.toml version.

This is ModeLab-style: version is a single source of truth in `pyproject.toml`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
REPOSITORY_URL = "https://github.com/MarKo7s/lasers.git"


def read_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not version:
        raise SystemExit(f"No [project].version in {PYPROJECT}")
    return str(version)


def extract_changelog_section(version: str) -> str:
    if not CHANGELOG.is_file():
        return f"Release lasers {version}"
    text = CHANGELOG.read_text(encoding="utf-8")
    header = re.search(
        rf"^## \[{re.escape(version)}\](?:\s[^\n]*)?\n",
        text,
        re.MULTILINE,
    )
    if not header:
        raise SystemExit(f"No CHANGELOG section for version {version} in {CHANGELOG}")
    start = header.end()
    next_section = re.search(r"^## \[", text[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(text)
    section = text[start:end].strip()
    return section or f"Release lasers {version}"


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(REPO_ROOT), text=True).strip()


def git_is_clean() -> bool:
    return run_git("status", "--porcelain") == ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="main", help="Branch to push before tagging")
    parser.add_argument(
        "--message",
        default="",
        help="Custom annotated tag message (overrides --from-changelog)",
    )
    parser.add_argument(
        "--from-changelog",
        action="store_true",
        help="Use CHANGELOG section as tag message body",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print git commands only")
    args = parser.parse_args()

    version = read_version()
    tag = f"v{version}"

    if not git_is_clean():
        raise SystemExit("Git tree is not clean. Commit or stash changes before releasing.")

    branch = args.branch

    if run_git("rev-parse", "--abbrev-ref", "HEAD") != branch:
        # Best-effort: push branch and tag from current HEAD if user asked for a non-matching branch.
        # Keep it simple and predictable for lab usage.
        pass

    if subprocess.call(["git", "show-ref", "--tags", "-q", tag], cwd=str(REPO_ROOT)) == 0:
        raise SystemExit(f"Tag {tag} already exists.")

    message = args.message.strip()
    if not message and args.from_changelog:
        message = extract_changelog_section(version)
    if not message:
        message = f"Release lasers {version}"

    commands: list[list[str]] = [
        ["git", "push", "origin", branch],
        ["git", "tag", "-a", tag, "-m", message],
        ["git", "push", "origin", tag],
    ]

    if args.dry_run:
        print("Dry-run commands:")
        for c in commands:
            print("  ", " ".join(c))
    else:
        for c in commands:
            subprocess.check_call(c, cwd=str(REPO_ROOT))

    install_hint = f'pip install "lasers[{ "pyside" }]" @ git+{REPOSITORY_URL}@{tag}'
    # The hint above is intentionally conservative; users can install extras as needed.
    print(f'Install hint: pip install "lasers @ git+{REPOSITORY_URL}@{tag}"')


if __name__ == "__main__":
    main()

