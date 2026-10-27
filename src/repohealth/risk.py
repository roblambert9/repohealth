"""License policy and risk assessment.

Model:

- :class:`Policy` — a corporate-style allowlist/denylist: ``denied`` SPDX
  ids fail the component, ``warn`` ids force a REVIEW, and
  ``fail_on_unknown`` (default off) turns unknown licenses into FAILs.
  An empty policy still runs the pairwise compatibility check.
- :class:`Assessment` — per-component findings plus pairwise conflict
  findings, aggregated into one verdict: FAIL if any FAIL finding exists,
  REVIEW if any REVIEW finding exists, otherwise PASS.
- Pairwise conflicts are computed over distinct licenses present, not over
  components, so a 200-dependency scan with two GPL versions produces one
  conflict finding, not thousands.

A REVIEW is never a pass. It means a human (or counsel) must look before
the component ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .licenses import LicenseInfo, UnknownLicense, pair_status
from .resolver import ResolvedDependency

PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"


@dataclass(frozen=True)
class Policy:
    denied: frozenset[str] = frozenset()
    warn: frozenset[str] = frozenset()
    fail_on_unknown: bool = False

    @classmethod
    def from_mapping(cls, mapping: dict) -> "Policy":
        return cls(
            denied=frozenset(mapping.get("denied", [])),
            warn=frozenset(mapping.get("warn", [])),
            fail_on_unknown=bool(mapping.get("fail_on_unknown", False)),
        )


@dataclass
class Finding:
    component: str  # Dependency name, or "pair: A + B" for conflicts.
    level: str  # PASS, REVIEW, or FAIL.
    reasons: list[str] = field(default_factory=list)


@dataclass
class Assessment:
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "counts": self.counts,
            "findings": [
                {"component": f.component, "level": f.level, "reasons": f.reasons}
                for f in self.findings
            ],
        }


def assess(resolved: list[ResolvedDependency], policy: Policy) -> Assessment:
    findings: list[Finding] = []
    for dep in resolved:
        license = dep.license
        if isinstance(license, UnknownLicense):
            level = FAIL if policy.fail_on_unknown else REVIEW
            findings.append(
                Finding(
                    component=dep.name,
                    level=level,
                    reasons=[f"unknown license: {license.reason} (resolver: {dep.resolver})"],
                )
            )
            continue
        if license.spdx_id in policy.denied:
            findings.append(
                Finding(
                    component=dep.name,
                    level=FAIL,
                    reasons=[f"license {license.spdx_id} is denied by policy"],
                )
            )
        elif license.spdx_id in policy.warn:
            findings.append(
                Finding(
                    component=dep.name,
                    level=REVIEW,
                    reasons=[f"license {license.spdx_id} is flagged for review by policy"],
                )
            )
        else:
            findings.append(
                Finding(component=dep.name, level=PASS, reasons=[f"license {license.spdx_id} ({license.tier})"])
            )

    seen_licenses: dict[str, LicenseInfo] = {}
    for dep in resolved:
        if isinstance(dep.license, LicenseInfo):
            seen_licenses.setdefault(dep.license.spdx_id, dep.license)
    ids = sorted(seen_licenses)
    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1 :]:
            status, reason = pair_status(seen_licenses[left_id], seen_licenses[right_id])
            if status == "conflict":
                findings.append(
                    Finding(component=f"pair: {left_id} + {right_id}", level=FAIL, reasons=[reason])
                )
            elif status == "review":
                findings.append(
                    Finding(component=f"pair: {left_id} + {right_id}", level=REVIEW, reasons=[reason])
                )

    counts = {PASS: 0, REVIEW: 0, FAIL: 0}
    for finding in findings:
        counts[finding.level] += 1
    if counts[FAIL]:
        verdict = FAIL
    elif counts[REVIEW]:
        verdict = REVIEW
    else:
        verdict = PASS
    return Assessment(verdict=verdict, findings=findings, counts=counts)
