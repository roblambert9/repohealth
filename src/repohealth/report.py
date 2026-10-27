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
from .testhealth import ERROR, FAILED, SKIPPED, TestRun
from .uptime import DOWN, UP, CheckResult

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


def render_test_markdown(run: TestRun, flaky: list[dict], history_runs: int) -> str:
    """Render a test-health report: totals, failures, then flaky cases."""
    totals = run.totals
    lines = [
        f"# repohealth test report: {run.source}",
        "",
        f"Total: {totals['total']} — passed {totals['passed']}, "
        f"failed {totals[FAILED]}, errors {totals[ERROR]}, "
        f"skipped {totals[SKIPPED]} — {run.duration:.1f}s",
        "",
    ]
    problems = [c for c in run.cases if c.outcome in (FAILED, ERROR)]
    if problems:
        lines.append("## Failures and errors")
        lines.append("")
        for case in problems:
            lines.append(f"- **{case.outcome}** `{case.id}`")
            if case.message:
                lines.append(f"  - {case.message}")
        lines.append("")
    if history_runs > 1:
        lines.append(f"## Flaky cases (across {history_runs} runs)")
        lines.append("")
        if flaky:
            for entry in flaky:
                lines.append(f"- `{entry['id']}` (seen in {entry['runs_seen']} runs)")
        else:
            lines.append("None — no case has both passing and failing runs.")
        lines.append("")
    return "\n".join(lines)


def render_uptime_markdown(results: list[CheckResult], summary: dict[str, dict]) -> str:
    """Render an uptime report: this run's checks, then history per target."""
    ups = sum(1 for r in results if r.status == UP)
    downs = sum(1 for r in results if r.status == DOWN)
    lines = [
        "# repohealth uptime report",
        "",
        f"This run: {ups} up, {downs} down.",
        "",
        "| Target | URL | Status | HTTP | Latency | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| {result.name} | {result.url} | {result.status} | "
            f"{result.http_status if result.http_status is not None else '—'} | "
            f"{result.latency_ms}ms | {result.error or '—'} |"
        )
    lines.append("")
    if summary:
        lines.append("## History")
        lines.append("")
        lines.append("| Target | Checks | Ups | Downs | Uptime | Last status |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for name, bucket in sorted(summary.items()):
            lines.append(
                f"| {name} | {bucket['checks']} | {bucket['ups']} | {bucket['downs']} | "
                f"{bucket['uptime_pct']}% | {bucket['last_status']} |"
            )
        lines.append("")
    return "\n".join(lines)
