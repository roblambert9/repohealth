"""CycloneDX 1.5 SBOM construction.

The SBOM is kept strictly standard: no risk data, no vendor extensions.
Risk lives in the assessment report (:mod:`repohealth.risk`,
:mod:`repohealth.report`), so the SBOM can be handed to any CycloneDX
consumer unchanged.

Component fields:

- ``bom-ref`` — stable within one document (``<ecosystem>:<name>@<version>``).
- ``purl`` — Package URL: ``pkg:pypi/<name>@<version>`` or
  ``pkg:npm/<name>@<version>`` (version omitted when unknown).
- ``licenses`` — ``{"license": {"id": <SPDX>}}`` when the license is known,
  ``{"license": {"name": <raw>}}`` when it is not, so unknown licenses stay
  visible instead of silently dropping the component.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import __version__
from .licenses import LicenseInfo
from .resolver import ResolvedDependency


def _purl(dep: ResolvedDependency) -> str:
    base = f"pkg:{dep.ecosystem}/{dep.name.lower()}"
    if dep.version:
        base += f"@{dep.version}"
    return base


def _bom_ref(dep: ResolvedDependency) -> str:
    base = f"{dep.ecosystem}:{dep.name.lower()}"
    if dep.version:
        base += f"@{dep.version}"
    return base


def build_cyclonedx(target: str, resolved: list[ResolvedDependency]) -> dict:
    """Build a CycloneDX 1.5 document for one scan."""
    components = []
    for dep in resolved:
        if isinstance(dep.license, LicenseInfo):
            licenses = [{"license": {"id": dep.license.spdx_id}}]
        else:
            licenses = [{"license": {"name": dep.license.raw or dep.name}}]
        component: dict = {
            "bom-ref": _bom_ref(dep),
            "type": "library",
            "name": dep.name,
            "licenses": licenses,
            "purl": _purl(dep),
        }
        if dep.version:
            component["version"] = dep.version
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "Nano Empire AI", "name": "repohealth", "version": __version__}],
            "component": {"type": "application", "name": target},
        },
        "components": components,
    }
