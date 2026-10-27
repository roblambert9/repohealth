"""HTTP uptime checks and an append-only incident log.

A target is UP when it answers with an HTTP status below 400 within the
timeout, DOWN otherwise (5xx, redirect loops, DNS failure, refused
connection, timeout). The rule is deliberately strict: a health endpoint
answering 404 is a service misbehaving, not a service up.

The log is a JSON list of check entries. Appends are atomic (temp file +
replace), the same pattern as the test-history file, so an interrupted
run never corrupts the log. Summaries are computed from the log, so
uptime percentages only mean something once a target has history.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

UP = "up"
DOWN = "down"


@dataclass(frozen=True)
class CheckResult:
    name: str
    url: str
    status: str  # "up" or "down".
    http_status: int | None
    latency_ms: float
    error: str
    checked_at: str


@dataclass
class UptimeSummary:
    per_target: dict[str, dict] = field(default_factory=dict)


def check_url(name: str, url: str, timeout: float = 10.0) -> CheckResult:
    """Perform one HTTP GET and classify the target."""
    started = datetime.now(timezone.utc)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "repohealth-uptime/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response.read(1)  # Confirm the body starts arriving.
    except urllib.error.HTTPError as exc:
        return _result(name, url, started, DOWN, exc.code, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _result(name, url, started, DOWN, None, str(exc))
    latency = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    if status_code < 400:
        return CheckResult(name, url, UP, status_code, round(latency, 1), "", started.isoformat())
    return _result(name, url, started, DOWN, status_code, f"HTTP {status_code}")


def _result(name, url, started, status, http_status, error):
    latency = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    return CheckResult(name, url, status, http_status, round(latency, 1), error, started.isoformat())


def run_checks(targets: list[tuple[str, str]], timeout: float = 10.0) -> list[CheckResult]:
    return [check_url(name, url, timeout=timeout) for name, url in targets]


def load_targets(config_path: str) -> list[tuple[str, str]]:
    """Load targets from JSON: a list of URLs, or of {"name", "url"} objects."""
    with open(config_path, encoding="utf-8") as handle:
        data = json.load(handle)
    targets = []
    if not isinstance(data, list):
        raise ValueError(f"uptime config is not a JSON list: {config_path}")
    for entry in data:
        if isinstance(entry, str):
            targets.append((entry, entry))
        elif isinstance(entry, dict) and "url" in entry:
            targets.append((entry.get("name", entry["url"]), entry["url"]))
        else:
            raise ValueError(f"unrecognized uptime target entry: {entry!r}")
    return targets


def result_to_entry(result: CheckResult) -> dict:
    return {
        "name": result.name,
        "url": result.url,
        "status": result.status,
        "http_status": result.http_status,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "checked_at": result.checked_at,
    }


def load_log(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"uptime log is not a JSON list: {path}")
    return data


def append_log(path: str, results: list[CheckResult]) -> list[dict]:
    log = load_log(path)
    log.extend(result_to_entry(r) for r in results)
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)
    os.replace(tmp_path, path)
    return log


def summarize(log: list[dict]) -> dict[str, dict]:
    """Per-target counts, uptime percentage, and last status."""
    summary: dict[str, dict] = {}
    for entry in log:
        name = entry.get("name", entry.get("url", "?"))
        bucket = summary.setdefault(
            name, {"url": entry.get("url", ""), "checks": 0, "ups": 0, "downs": 0,
                   "last_status": None, "last_checked": None}
        )
        bucket["checks"] += 1
        if entry.get("status") == UP:
            bucket["ups"] += 1
        else:
            bucket["downs"] += 1
        bucket["last_status"] = entry.get("status")
        bucket["last_checked"] = entry.get("checked_at")
    for bucket in summary.values():
        checks = bucket["checks"]
        bucket["uptime_pct"] = round(100.0 * bucket["ups"] / checks, 1) if checks else 0.0
    return summary
