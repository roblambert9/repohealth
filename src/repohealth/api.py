"""HTTP API (local demo use).

POST /scan runs a full scan and returns the verdict, the assessment, the
CycloneDX SBOM, and the Markdown report in one response. GET /health
reports liveness.

Security note: /scan reads local paths and clones public GitHub URLs on
behalf of the caller. Bind loopback only (the CLI default) and never
expose this service to untrusted networks.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import __version__
from .report import render_markdown, render_test_markdown, render_uptime_markdown
from .resolver import ChainedResolver, InstalledMetadataResolver, PyPIResolver, StubResolver
from .risk import Policy, assess
from .sbom import build_cyclonedx
from .scan import ScanError, scan_target
from .testhealth import TestHealthError, detect_flaky, parse_junit_xml, run_to_history_entry
from .uptime import DOWN, run_checks, summarize

app = FastAPI(title="repohealth", version=__version__)


class ScanRequest(BaseModel):
    target: str
    policy: dict | None = None
    stub_map: dict[str, str] | None = None


class ScanResponse(BaseModel):
    target: str
    verdict: str
    counts: dict[str, int]
    findings: list[dict]
    sbom: dict
    report_markdown: str
    warnings: list[str]


class TestHealthRequest(BaseModel):
    junit_xml: str


class TestHealthResponse(BaseModel):
    source: str
    totals: dict[str, int]
    duration: float
    failures: list[dict]
    flaky: list[dict]
    report_markdown: str


class UptimeTarget(BaseModel):
    name: str | None = None
    url: str


class UptimeRequest(BaseModel):
    targets: list[UptimeTarget]
    timeout: float = 10.0


class UptimeResponse(BaseModel):
    results: list[dict]
    history: dict[str, dict]
    report_markdown: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/uptime", response_model=UptimeResponse)
def uptime(request: UptimeRequest) -> UptimeResponse:
    targets = [(t.name or t.url, t.url) for t in request.targets]
    results = run_checks(targets, timeout=request.timeout)
    history = summarize([{"name": r.name, "url": r.url, "status": r.status,
                          "checked_at": r.checked_at} for r in results])
    return UptimeResponse(
        results=[{"name": r.name, "url": r.url, "status": r.status,
                  "http_status": r.http_status, "latency_ms": r.latency_ms,
                  "error": r.error} for r in results],
        history=history,
        report_markdown=render_uptime_markdown(results, history),
    )


@app.post("/test-health", response_model=TestHealthResponse)
def test_health(request: TestHealthRequest) -> TestHealthResponse:
    try:
        run = parse_junit_xml(request.junit_xml, source="api-upload")
    except TestHealthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    history = [run_to_history_entry(run)]
    return TestHealthResponse(
        source=run.source,
        totals=run.totals,
        duration=round(run.duration, 1),
        failures=[
            {"id": c.id, "outcome": c.outcome, "message": c.message}
            for c in run.cases
            if c.outcome in ("failed", "error")
        ],
        flaky=detect_flaky(history),
        report_markdown=render_test_markdown(run, [], 1),
    )


@app.post("/scan", response_model=ScanResponse)
def scan(request: ScanRequest) -> ScanResponse:
    policy = Policy.from_mapping(request.policy) if request.policy else Policy()
    if request.stub_map is not None:
        resolver = StubResolver(request.stub_map)
    else:
        resolver = ChainedResolver([InstalledMetadataResolver(), PyPIResolver()])
    try:
        result = scan_target(request.target, resolver)
    except ScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assessment = assess(result.resolved, policy)
    return ScanResponse(
        target=result.target,
        verdict=assessment.verdict,
        counts=assessment.counts,
        findings=[
            {"component": f.component, "level": f.level, "reasons": f.reasons}
            for f in assessment.findings
        ],
        sbom=build_cyclonedx(result.target, result.resolved),
        report_markdown=render_markdown(result.target, result.resolved, assessment, result.warnings),
        warnings=result.warnings,
    )
