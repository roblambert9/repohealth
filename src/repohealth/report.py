"""Human-readable and machine-readable assessment reports.

The Markdown report is the artifact a reviewer opens: verdict first,
counts, then every non-PASS finding with its reasons, then the full
component inventory. The JSON summary mirrors the same data for tooling.

Every Markdown report ends with the same disclaimer. Automated license
inventory is not a legal opinion; a FAIL or REVIEW is a prompt for a
human (or counsel), not a verdict about the law.
"""

from __future__ import annotations

from .resolver import ResolvedDependency
from .risk import FAIL, PASS, REVIEW, Assessment

DISCLAIMER = (
    "> Disclaimer: this report is an automated dependency inventory and "
    "license-compatibility aid. It is not legal advice, and a PASS is not a "
    "legal opinion that a combination is lawful. Confirm REVIEW and FAIL "
    "findings with counsel before shipping."
)


def render_markdown(
    target: str,
    resolved: list[ResolvedDependency],
    assessment: Assessment,
    warnings: list[str],
) -> str:
    lines = [
        f"# repohealth report: {target}",
        "",
        f"**Verdict: {assessment.verdict}**",
        "",
        f"Components: {len(resolved)} — "
        f"PASS {assessment.counts.get(PASS, 0)}, "
        f"REVIEW {assessment.counts.get(REVIEW, 0)}, "
        f"FAIL {assessment.counts.get(FAIL, 0)}",
        "",
    ]
    problems = [f for f in assessment.findings if f.level != PASS]
    if problems:
        lines.append("## Findings requiring attention")
        lines.append("")
        for finding in problems:
            lines.append(f"- **{finding.level}** `{finding.component}`")
            for reason in finding.reasons:
                lines.append(f"  - {reason}")
        lines.append("")
    lines.append("## Component inventory")
    lines.append("")
    lines.append("| Component | Version | License | Resolver |")
    lines.append("| --- | --- | --- | --- |")
    for dep in resolved:
        license_label = dep.license.spdx_id if dep.license.spdx_id else f"unknown ({dep.license.raw})"
        lines.append(
            f"| {dep.name} | {dep.version or '—'} | {license_label} | {dep.resolver} |"
        )
    lines.append("")
    if warnings:
        lines.append("## Parser warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    return "\n".join(lines)
