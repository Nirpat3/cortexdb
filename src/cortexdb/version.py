"""
Self-Versioning System for CortexDB.

Single source of truth: __version__ in cortexdb/__init__.py
This module provides:
  - Version reading from the canonical source
  - Semantic version bumping (major, minor, patch)
  - Automatic CHANGELOG.md generation
  - Sync of version across all files that reference it
"""

import re
import time
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # project root
INIT_FILE = ROOT_DIR / "src" / "cortexdb" / "__init__.py"
PYPROJECT_FILE = ROOT_DIR / "pyproject.toml"
CHANGELOG_FILE = ROOT_DIR / "CHANGELOG.md"

# Files that contain hardcoded version strings to sync
VERSION_SYNC_TARGETS = [
    (ROOT_DIR / "src" / "cortexdb" / "server.py", r'version="[\d.]+"', 'version="{version}"'),
    (ROOT_DIR / "src" / "cortexdb" / "core" / "database.py", r'"version":\s*"[\d.]+"', '"version": "{version}"'),
    (ROOT_DIR / "src" / "cortexdb" / "agents" / "service_monitor.py",
     r'"cortexdb-server",\s*"CortexDB Server",\s*5400,\s*"[\d.]+"',
     '"cortexdb-server", "CortexDB Server", 5400, "{version}"'),
    (PYPROJECT_FILE, r'version\s*=\s*"[\d.]+"', 'version = "{version}"'),
]

BumpType = Literal["major", "minor", "patch"]


def get_version() -> str:
    """Read current version from __init__.py."""
    text = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([\d.]+)"', text)
    if not match:
        raise RuntimeError(f"Cannot find __version__ in {INIT_FILE}")
    return match.group(1)


def parse_version(version: str) -> tuple:
    """Parse semver string into (major, minor, patch)."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(bump: BumpType, reason: str = "", changes: list = None) -> str:
    """
    Bump version, sync all files, and append to CHANGELOG.

    Args:
        bump: "major", "minor", or "patch"
        reason: Short summary of why the version was bumped
        changes: List of change descriptions for the changelog

    Returns:
        The new version string
    """
    old_version = get_version()
    major, minor, patch = parse_version(old_version)

    if bump == "major":
        new_version = f"{major + 1}.0.0"
    elif bump == "minor":
        new_version = f"{major}.{minor + 1}.0"
    else:
        new_version = f"{major}.{minor}.{patch + 1}"

    # Update __init__.py (canonical source)
    _update_file(
        INIT_FILE,
        rf'__version__\s*=\s*"{re.escape(old_version)}"',
        f'__version__ = "{new_version}"',
    )

    # Sync all other files
    sync_count = _sync_version(new_version)

    # Update CHANGELOG
    _update_changelog(new_version, old_version, bump, reason, changes or [])

    logger.info(
        "Version bumped: %s -> %s (%s) — synced %d files",
        old_version, new_version, bump, sync_count,
    )
    return new_version


def sync_all() -> int:
    """Sync current version to all files. Returns count of files updated."""
    version = get_version()
    return _sync_version(version)


def _sync_version(version: str) -> int:
    """Write version to all sync targets. Returns count of files updated."""
    count = 0
    for filepath, pattern, replacement in VERSION_SYNC_TARGETS:
        if not filepath.exists():
            logger.warning("Version sync target not found: %s", filepath)
            continue
        updated = _update_file(filepath, pattern, replacement.format(version=version))
        if updated:
            count += 1
    return count


def _update_file(filepath: Path, pattern: str, replacement: str) -> bool:
    """Replace first occurrence of pattern in file. Returns True if changed."""
    text = filepath.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, count=1)
    if n > 0 and new_text != text:
        filepath.write_text(new_text, encoding="utf-8")
        return True
    return False


def _update_changelog(new_version: str, old_version: str, bump: BumpType,
                      reason: str, changes: list):
    """Prepend a new entry to CHANGELOG.md."""
    date_str = time.strftime("%Y-%m-%d")
    entry_lines = [
        f"## [{new_version}] - {date_str}",
        "",
    ]
    if reason:
        entry_lines.append(f"**{reason}**")
        entry_lines.append("")

    bump_labels = {"major": "BREAKING", "minor": "Feature", "patch": "Fix"}
    entry_lines.append(f"Type: {bump_labels[bump]} ({bump})")
    entry_lines.append(f"Previous: {old_version}")
    entry_lines.append("")

    if changes:
        entry_lines.append("### Changes")
        for change in changes:
            entry_lines.append(f"- {change}")
        entry_lines.append("")

    entry_lines.append("---")
    entry_lines.append("")

    new_entry = "\n".join(entry_lines)

    if CHANGELOG_FILE.exists():
        existing = CHANGELOG_FILE.read_text(encoding="utf-8")
        # Insert after the header
        if existing.startswith("# "):
            header_end = existing.index("\n") + 1
            content = existing[:header_end] + "\n" + new_entry + existing[header_end:]
        else:
            content = new_entry + existing
    else:
        content = "# CortexDB Changelog\n\n" + new_entry

    CHANGELOG_FILE.write_text(content, encoding="utf-8")


def get_changelog(limit: int = 10) -> str:
    """Read the last N changelog entries."""
    if not CHANGELOG_FILE.exists():
        return "No changelog found."
    text = CHANGELOG_FILE.read_text(encoding="utf-8")
    sections = re.split(r"\n---\n", text)
    return "\n---\n".join(sections[:limit + 1])
