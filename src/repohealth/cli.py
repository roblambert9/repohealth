"""Command-line interface.

Usage::

    repohealth scan <path-or-github-url> [--policy policy.json]
                [--sbom sbom.json] [--report report.md] [--summary-json summary.json]
                [--stub-map stub.json]
    repohealth test-health <junit.xml> [--history history.json]
                [--report report.md] [--summary-json summary.json]
    repohealth serve [--host 127.0.0.1] [--port 8000]

Exit codes for scan: 0 = PASS, 2 = REVIEW, 3 = FAIL, 1 = scan or input error.
Exit codes for test-health: 0 = no failures or errors, 2 = failures or
errors present, 1 = input error.
``--stub-map`` supplies a JSON name -> license map and replaces the live
resolvers, which makes demo and test runs deterministic without network
access. Without it, the resolver chain is installed metadata, then PyPI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import render_markdown, render_test_markdown
from .resolver import ChainedResolver, InstalledMetadataResolver, PyPIResolver, StubResolver
from .risk import FAIL, PASS, REVIEW, Policy, assess
from .sbom import build_cyclonedx
from .scan import ScanError, scan_target
from .testhealth import (
    TestHealthError,
    append_history,
    detect_flaky,
    parse_junit_xml,
    run_to_history_entry,
)


def _build_resolver(stub_map: dict[str, str] | None):
    if stub_map is not None:
        return StubResolver(stub_map)
    return ChainedResolver([InstalledMetadataResolver(), PyPIResolver()])


def _load_json(path: str, what: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanError(f"cannot read {what} file {path}: {exc}") from exc


def _cmd_scan(args: argparse.Namespace) -> int:
    policy = Policy()
    if args.policy:
        policy = Policy.from_mapping(_load_json(args.policy, "policy"))
    stub_map = _load_json(args.stub_map, "stub map") if args.stub_map else None
    resolver = _build_resolver(stub_map)
    try:
        result = scan_target(args.target, resolver)
    except ScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    assessment = assess(result.resolved, policy)
    sbom = build_cyclonedx(result.target, result.resolved)
    markdown = render_markdown(result.target, result.resolved, assessment, result.warnings)
    if args.sbom:
        Path(args.sbom).write_text(json.dumps(sbom, indent=2), encoding="utf-8")
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(assessment.to_dict(), indent=2), encoding="utf-8")
    if args.report:
        Path(args.report).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    print(f"verdict: {assessment.verdict} "
          f"(PASS {assessment.counts.get(PASS, 0)}, "
          f"REVIEW {assessment.counts.get(REVIEW, 0)}, "
          f"FAIL {assessment.counts.get(FAIL, 0)})", file=sys.stderr)
    return {"PASS": 0, REVIEW: 2, FAIL: 3}[assessment.verdict]


def _cmd_test_health(args: argparse.Namespace) -> int:
    try:
        text = Path(args.junit_xml).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read JUnit file: {exc}", file=sys.stderr)
        return 1
    try:
        run = parse_junit_xml(text, source=args.junit_xml)
    except TestHealthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.history:
        try:
            history = append_history(args.history, run)
        except (OSError, TestHealthError, json.JSONDecodeError) as exc:
            print(f"error: history file unusable: {exc}", file=sys.stderr)
            return 1
    else:
        history = [run_to_history_entry(run)]
    flaky = detect_flaky(history)
    markdown = render_test_markdown(run, flaky, len(history))
    summary = {"source": run.source, "totals": run.totals,
               "duration": round(run.duration, 1), "flaky": flaky}
    if args.report:
        Path(args.report).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"tests: {run.totals['total']} total, {run.totals['failed']} failed, "
          f"{run.totals['error']} errors, {len(flaky)} flaky", file=sys.stderr)
    return 2 if run.has_failures else 0


def _cmd_serve(args: argparse.Namespace) -> int:
    # Imported lazily so the core scanner never requires FastAPI installed.
    import uvicorn

    from .api import app

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repohealth", description="Repository health, license, and SBOM scanner.")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Scan a directory, manifest file, or GitHub URL.")
    scan.add_argument("target", help="Local path or https://github.com/... URL")
    scan.add_argument("--policy", help="JSON policy file (denied/warn/fail_on_unknown)")
    scan.add_argument("--sbom", help="Write the CycloneDX SBOM JSON here")
    scan.add_argument("--report", help="Write the Markdown report here (default: stdout)")
    scan.add_argument("--summary-json", help="Write the assessment JSON here")
    scan.add_argument("--stub-map", help="JSON name -> license map replacing live resolvers")
    scan.set_defaults(func=_cmd_scan)
    health = sub.add_parser("test-health", help="Analyze a JUnit XML test run.")
    health.add_argument("junit_xml", help="JUnit XML file (e.g. pytest --junitxml output)")
    health.add_argument("--history", help="JSON history file to append this run to (enables flaky detection)")
    health.add_argument("--report", help="Write the Markdown report here (default: stdout)")
    health.add_argument("--summary-json", help="Write the JSON summary here")
    health.set_defaults(func=_cmd_test_health)
    serve = sub.add_parser("serve", help="Run the HTTP API (local demo use; binds loopback by default).")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
