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
from .report import render_markdown
from .resolver import ChainedResolver, InstalledMetadataResolver, PyPIResolver, StubResolver
from .risk import Policy, assess
from .sbom import build_cyclonedx
from .scan import ScanError, scan_target

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


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
