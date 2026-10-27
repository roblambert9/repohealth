"""Dependency manifest parsers.

Supported manifests (v1):

- ``requirements.txt`` — pip requirement lines. Option lines (``-r``,
  ``--index-url``, ...) are recorded as warnings and skipped; environment
  markers (``; python_version < ...``) are stripped; extras
  (``name[extra]==1.0``) are stripped to the base package name.
- ``pyproject.toml`` — PEP 621 ``[project] dependencies`` plus
  ``[project.optional-dependencies]`` groups (flagged as dev).
- ``package.json`` — ``dependencies`` and ``devDependencies``. Leading
  ``^``, ``~``, ``>=``, ``<=``, ``>``, ``<``, ``=``, ``v`` characters are
  stripped to a version guess; the raw spec is kept alongside.

Parsers never touch the network and never guess a version: when no pinned
version exists, ``version`` is ``None`` and the resolver decides.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str | None  # Pinned version when one is stated, else None.
    spec: str  # Raw version specifier as written, "" when bare.
    ecosystem: str  # "pypi" or "npm".
    source: str  # Manifest filename the entry came from.
    dev: bool = False


@dataclass
class ParseResult:
    dependencies: list[Dependency] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$")
_VERSION_RE = re.compile(r"(==|===|>=|<=|~=|!=|>|<)\s*([^\s;,]+)")


def _split_name_spec(line: str) -> tuple[str, str, str | None] | None:
    """Split one requirement line into (name, spec, pinned version)."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    match = _NAME_RE.match(line)
    if not match:
        return None
    name, _extras, rest = match.groups()
    rest = rest.split(";", 1)[0].strip()  # Environment marker.
    pinned = None
    for operator, version in _VERSION_RE.findall(rest):
        if operator == "==":
            pinned = version.strip()
            break
    return name, rest, pinned


def parse_requirements_txt(text: str, source: str = "requirements.txt") -> ParseResult:
    result = ParseResult()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-") or line.startswith("--"):
            result.warnings.append(f"{source}:{lineno}: skipped option line: {line}")
            continue
        parsed = _split_name_spec(line)
        if parsed is None:
            result.warnings.append(f"{source}:{lineno}: unparsable line: {line}")
            continue
        name, spec, pinned = parsed
        result.dependencies.append(
            Dependency(name=name, version=pinned, spec=spec, ecosystem="pypi", source=source)
        )
    return result


def parse_pyproject_toml(text: str, source: str = "pyproject.toml") -> ParseResult:
    result = ParseResult()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        result.warnings.append(f"{source}: invalid TOML: {exc}")
        return result
    project = data.get("project", {})
    for entry in project.get("dependencies", []):
        parsed = _split_name_spec(entry)
        if parsed is None:
            result.warnings.append(f"{source}: unparsable dependency: {entry}")
            continue
        name, spec, pinned = parsed
        result.dependencies.append(
            Dependency(name=name, version=pinned, spec=spec, ecosystem="pypi", source=source)
        )
    for group, entries in (project.get("optional-dependencies", {}) or {}).items():
        for entry in entries:
            parsed = _split_name_spec(entry)
            if parsed is None:
                result.warnings.append(f"{source}: unparsable dependency in [{group}]: {entry}")
                continue
            name, spec, pinned = parsed
            result.dependencies.append(
                Dependency(name=name, version=pinned, spec=spec, ecosystem="pypi", source=source, dev=True)
            )
    return result


def _npm_version(raw: str) -> tuple[str, str | None]:
    spec = raw.strip()
    guess = re.sub(r"^[\^~>=<v=\s]+", "", spec)
    guess = guess.split(" ")[0] if guess else ""
    return spec, (guess or None)


def parse_package_json(text: str, source: str = "package.json") -> ParseResult:
    result = ParseResult()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        result.warnings.append(f"{source}: invalid JSON: {exc}")
        return result
    for section, dev in (("dependencies", False), ("devDependencies", True)):
        for name, raw in (data.get(section, {}) or {}).items():
            spec, guess = _npm_version(str(raw))
            result.dependencies.append(
                Dependency(name=name, version=guess, spec=spec, ecosystem="npm", source=source, dev=dev)
            )
    return result
