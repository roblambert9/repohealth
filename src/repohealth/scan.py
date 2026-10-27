"""Scan orchestration: manifest discovery, parsing, and resolution.

The CLI and the API share this module so a scan means the same thing in
both. Discovery skips hidden directories, virtualenvs, and build output;
duplicate dependencies (same ecosystem, same name) collapse to one entry,
preferring a pinned version when one manifest pins and another does not.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .parsers import (
    Dependency,
    ParseResult,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
)
from .resolver import ResolvedDependency, Resolver

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".tox"}
_REQUIREMENTS_RE = re.compile(r"^requirements.*\.txt$")


class ScanError(Exception):
    """Raised when a scan target cannot be read or cloned."""


@dataclass
class ScanResult:
    target: str
    resolved: list[ResolvedDependency] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parser_for(filename: str):
    if _REQUIREMENTS_RE.match(filename):
        return parse_requirements_txt
    if filename == "pyproject.toml":
        return parse_pyproject_toml
    if filename == "package.json":
        return parse_package_json
    return None


def discover_manifests(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for filename in sorted(filenames):
            if _parser_for(filename) is not None:
                found.append(Path(dirpath) / filename)
    return sorted(found)


def _parse_manifest(path: Path) -> ParseResult:
    parser = _parser_for(path.name)
    if parser is None:
        return ParseResult(warnings=[f"unsupported manifest: {path}"])
    return parser(path.read_text(encoding="utf-8", errors="replace"), source=path.name)


def _dedupe(dependencies: list[Dependency]) -> tuple[list[Dependency], list[str]]:
    """Collapse duplicates by (ecosystem, name), preferring pinned versions."""
    warnings: list[str] = []
    by_key: dict[tuple[str, str], Dependency] = {}
    for dep in dependencies:
        key = (dep.ecosystem, dep.name.lower())
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dep
        elif existing.version is None and dep.version is not None:
            by_key[key] = dep
        elif (
            existing.version is not None
            and dep.version is not None
            and existing.version != dep.version
        ):
            warnings.append(
                f"conflicting pinned versions for {dep.name}: "
                f"{existing.version} (kept) vs {dep.version} (from {dep.source})"
            )
    return list(by_key.values()), warnings


def scan_paths(paths: list[Path], resolver: Resolver) -> tuple[list[ResolvedDependency], list[str]]:
    dependencies: list[Dependency] = []
    warnings: list[str] = []
    for path in paths:
        parsed = _parse_manifest(path)
        dependencies.extend(parsed.dependencies)
        warnings.extend(parsed.warnings)
    deduped, dedupe_warnings = _dedupe(dependencies)
    warnings.extend(dedupe_warnings)
    return [resolver.resolve(dep) for dep in deduped], warnings


def clone_github_url(url: str, parent: Path) -> Path:
    """Shallow-clone a public GitHub URL into a fresh directory."""
    if shutil.which("git") is None:
        raise ScanError("git is required to scan a GitHub URL but was not found")
    dest = parent / "repo"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ScanError(f"git clone failed for {url}: {result.stderr.strip()}")
    return dest


def scan_target(target: str, resolver: Resolver) -> ScanResult:
    """Scan a local path, a single manifest file, or a GitHub URL."""
    if target.startswith("https://github.com/") or target.startswith("git@github.com:"):
        with tempfile.TemporaryDirectory(prefix="repohealth-") as tmpdir:
            cloned = clone_github_url(target, Path(tmpdir))
            resolved, warnings = scan_paths(discover_manifests(cloned), resolver)
            return ScanResult(target=target, resolved=resolved, warnings=warnings)
    path = Path(target)
    if not path.exists():
        raise ScanError(f"scan target does not exist: {target}")
    if path.is_file():
        resolved, warnings = scan_paths([path], resolver)
        return ScanResult(target=target, resolved=resolved, warnings=warnings)
    resolved, warnings = scan_paths(discover_manifests(path), resolver)
    return ScanResult(target=target, resolved=resolved, warnings=warnings)
