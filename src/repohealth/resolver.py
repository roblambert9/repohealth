"""License resolvers: turn a dependency into a resolved license.

Resolvers are small, single-purpose, and chained: :class:`ChainedResolver`
tries each resolver in order and keeps the first answer that actually names
a license. A resolver that cannot answer returns an unknown license instead
of raising, so one unreachable registry never kills a whole scan.

Implementations:

- :class:`InstalledMetadataResolver` — reads ``importlib.metadata`` for
  locally installed distributions (license expression, else the first
  OSI-approved trove classifier).
- :class:`PyPIResolver` — queries the public PyPI JSON API (stdlib
  ``urllib`` only, 10s timeout). Network failure degrades to unknown.
- :class:`StubResolver` — fixed name -> license map. Used by the test suite
  and by ``--stub-map`` demo runs so results are deterministic without
  network access.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from typing import Protocol

from .licenses import License, UnknownLicense, normalize
from .parsers import Dependency


@dataclass(frozen=True)
class ResolvedDependency:
    name: str
    version: str | None
    spec: str
    ecosystem: str
    source: str
    dev: bool
    license: License
    resolver: str


class Resolver(Protocol):
    def resolve(self, dep: Dependency) -> ResolvedDependency: ...


def _resolved(dep: Dependency, license: License, resolver: str) -> ResolvedDependency:
    return ResolvedDependency(
        name=dep.name,
        version=dep.version,
        spec=dep.spec,
        ecosystem=dep.ecosystem,
        source=dep.source,
        dev=dep.dev,
        license=license,
        resolver=resolver,
    )


def _from_classifiers(classifiers: list[str]) -> License | None:
    for classifier in classifiers:
        if classifier.startswith("License :: OSI Approved ::"):
            candidate = normalize(classifier)
            if not isinstance(candidate, UnknownLicense):
                return candidate
    return None


class InstalledMetadataResolver:
    """Resolve from locally installed package metadata."""

    name = "installed-metadata"

    def resolve(self, dep: Dependency) -> ResolvedDependency:
        if dep.ecosystem != "pypi":
            return _resolved(dep, UnknownLicense(dep.name, "not a PyPI package"), self.name)
        try:
            dist = importlib_metadata.distribution(dep.name)
        except importlib_metadata.PackageNotFoundError:
            return _resolved(dep, UnknownLicense(dep.name, "package not installed locally"), self.name)
        meta = dist.metadata
        expression = meta.get("License-Expression")
        if expression:
            return _resolved(dep, normalize(expression), self.name)
        classifiers = list(meta.get_all("Classifier") or [])
        found = _from_classifiers(classifiers)
        if found is not None:
            return _resolved(dep, found, self.name)
        raw_license = meta.get("License")
        if raw_license:
            return _resolved(dep, normalize(raw_license), self.name)
        return _resolved(dep, UnknownLicense(dep.name, "installed metadata names no license"), self.name)


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


class PyPIResolver:
    """Resolve via the public PyPI JSON API. Failures degrade to unknown."""

    name = "pypi"
    timeout_secs = 10

    def resolve(self, dep: Dependency) -> ResolvedDependency:
        if dep.ecosystem != "pypi":
            return _resolved(dep, UnknownLicense(dep.name, "not a PyPI package"), self.name)
        path = _pep503(dep.name)
        if dep.version:
            path += f"/{dep.version}"
        url = f"https://pypi.org/pypi/{path}/json"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "repohealth/0.1.0"})
            with urllib.request.urlopen(request, timeout=self.timeout_secs) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            return _resolved(dep, UnknownLicense(dep.name, f"PyPI lookup failed: {exc}"), self.name)
        info = payload.get("info", {})
        raw_license = info.get("license")
        if raw_license:
            candidate = normalize(raw_license)
            if not isinstance(candidate, UnknownLicense):
                return _resolved(dep, candidate, self.name)
        found = _from_classifiers(info.get("classifiers", []))
        if found is not None:
            return _resolved(dep, found, self.name)
        if raw_license:
            return _resolved(dep, normalize(raw_license), self.name)
        return _resolved(dep, UnknownLicense(dep.name, "PyPI record names no license"), self.name)


class StubResolver:
    """Fixed name -> license map for tests and deterministic demos."""

    name = "stub"

    def __init__(self, mapping: dict[str, str]):
        self.mapping = {key.lower(): value for key, value in mapping.items()}

    def resolve(self, dep: Dependency) -> ResolvedDependency:
        raw = self.mapping.get(dep.name.lower())
        if raw is None:
            return _resolved(dep, UnknownLicense(dep.name, "not in stub map"), self.name)
        return _resolved(dep, normalize(raw), self.name)


class ChainedResolver:
    """First resolver that names a license wins."""

    name = "chained"

    def __init__(self, resolvers: list[Resolver]):
        self.resolvers = resolvers

    def resolve(self, dep: Dependency) -> ResolvedDependency:
        last: ResolvedDependency | None = None
        for resolver in self.resolvers:
            resolved = resolver.resolve(dep)
            last = resolved
            if not isinstance(resolved.license, UnknownLicense):
                return resolved
        assert last is not None  # A chain is never constructed empty.
        return last
