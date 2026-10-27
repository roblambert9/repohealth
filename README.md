# repohealth

A repository health, license-compliance, and SBOM scanner. Point it at a
directory, a manifest file, or a public GitHub URL and it produces:

- A **CycloneDX 1.5 SBOM** — a standard software bill of materials for the
  dependency tree.
- A **license-risk assessment** — every component mapped to a real SPDX
  identifier, checked against a corporate-style policy (denied / warned
  licenses), and checked pairwise for version-family conflicts
  (GPL-2.0-only vs GPL-3.0-only, LGPL/GPL version mismatches).
- A **human-readable report** — verdict first, then every finding that
  needs attention, then the full component inventory.

Unknown or ambiguous license strings are never guessed into a safe tier.
They become REVIEW findings. A REVIEW is a human task, not a pass.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Scan the demo app (deterministic: uses the stub license map)
repohealth scan examples/demo-app \
  --stub-map examples/demo-stub-map.json \
  --policy examples/policy-deny-strong-copyleft.json \
  --sbom /tmp/sbom.json --report /tmp/report.md

# Scan any local project or public repo (live resolvers: installed metadata, then PyPI)
repohealth scan /path/to/project --sbom sbom.json
repohealth scan https://github.com/owner/repo --sbom sbom.json

# HTTP API (loopback only; local demo use)
repohealth serve
curl -X POST localhost:8000/scan -H 'Content-Type: application/json' \
  -d '{"target": "examples/demo-app", "stub_map": {"requests": "Apache-2.0"}}'
```

Exit codes: `0` PASS, `2` REVIEW, `3` FAIL, `1` scan or input error.

## Supported manifests

| Manifest | Ecosystems |
| --- | --- |
| `requirements*.txt` | PyPI |
| `pyproject.toml` (PEP 621 deps + optional groups) | PyPI |
| `package.json` (dependencies + devDependencies) | npm |

## Architecture

| Module | Job |
| --- | --- |
| `repohealth/licenses.py` | SPDX catalog, string normalization, pairwise compatibility model |
| `repohealth/parsers.py` | Manifest parsers (stdlib only, no network) |
| `repohealth/resolver.py` | License resolvers: installed metadata, PyPI JSON API, stub, chained |
| `repohealth/scan.py` | Discovery, dedup, GitHub cloning, shared scan flow |
| `repohealth/sbom.py` | CycloneDX 1.5 document construction (standard-clean, no risk data) |
| `repohealth/risk.py` | Policy + assessment (verdict aggregation) |
| `repohealth/report.py` | Markdown + JSON reporting |
| `repohealth/cli.py` | CLI (`scan`, `serve`) |
| `repohealth/api.py` | FastAPI service |

The core (parsers, licenses, risk, SBOM, reporters) is standard-library
only. FastAPI is required only for `serve`.

## License model

Tiers: permissive (MIT, Apache-2.0, BSD, ISC, ...), weak copyleft
(MPL-2.0, LGPL), strong copyleft (GPL), network copyleft (AGPL).
Permissive licenses combine freely. Same-license pairs are compatible.
Known version-family mismatches conflict. Combinations that depend on
secondary-license notices or linking details the scanner cannot see
(notably MPL-2.0 with GPL-family licenses) return REVIEW.

> Disclaimer: this tool is an automated inventory aid, not legal advice.
> Confirm REVIEW and FAIL findings with counsel before shipping.

## Policy file

```json
{
  "denied": ["GPL-3.0-only", "AGPL-3.0-only"],
  "warn": ["LGPL-3.0-only", "MPL-2.0"],
  "fail_on_unknown": false
}
```

## Sample output

`examples/sample-report.md` and `examples/sample-sbom.json` are real
outputs of the demo scan above (stub map, deny-strong-copyleft policy).
The demo intentionally includes one GPL-3.0-only component, so the sample
verdict is FAIL — that is the tool working, not a broken sample.

## Roadmap

- **Test-health slice:** ingest pytest JUnit XML, track pass/fail, coverage,
  and flaky tests over time.
- **Uptime slice:** HTTP health checks with an incident log and automated
  status output.
- npm license resolution via the npm registry (currently parsed, resolved
  as unknown unless a stub map names the license).

## License

MIT. See `LICENSE`.
