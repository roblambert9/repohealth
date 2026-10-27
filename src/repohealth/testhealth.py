"""JUnit XML test-health analysis: per-run summary plus cross-run flakiness.

A test run is parsed from JUnit XML (the format ``pytest --junitxml`` and
most CI runners emit). Outcomes are derived from the case elements
themselves, not from suite-level counters, so a hand-edited or partial
report cannot inflate the pass count.

Flakiness needs history: a case is flaky when it has both a good outcome
(passed) and a bad outcome (failed or errored) across runs. Skipped runs
never make a case flaky — a test that skipped once and passed once is
stable, not flaky.

History is a JSON list of runs, each ``{"source": ..., "cases":
[{"id": ..., "outcome": ...}]}``. Appends are atomic (temp file +
replace) so an interrupted write never corrupts the history.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

PASSED = "passed"
FAILED = "failed"
ERROR = "error"
SKIPPED = "skipped"
GOOD = {PASSED}
BAD = {FAILED, ERROR}


@dataclass(frozen=True)
class TestCase:
    id: str  # "classname::name"
    classname: str
    name: str
    outcome: str
    duration: float
    message: str = ""


@dataclass
class TestRun:
    source: str
    cases: list[TestCase] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        counts = {PASSED: 0, FAILED: 0, ERROR: 0, SKIPPED: 0}
        for case in self.cases:
            counts[case.outcome] += 1
        counts["total"] = len(self.cases)
        return counts

    @property
    def duration(self) -> float:
        return sum(case.duration for case in self.cases)

    @property
    def has_failures(self) -> bool:
        return any(case.outcome in BAD for case in self.cases)


class TestHealthError(Exception):
    """Raised when JUnit XML cannot be parsed."""

    __test__ = False  # pytest collects Test*-named classes; this is not one.


def _case_outcome(element: ET.Element) -> tuple[str, str]:
    failure = element.find("failure")
    if failure is not None:
        return FAILED, (failure.get("message") or (failure.text or "").strip())
    error = element.find("error")
    if error is not None:
        return ERROR, (error.get("message") or (error.text or "").strip())
    if element.find("skipped") is not None:
        return SKIPPED, ""
    return PASSED, ""


def parse_junit_xml(text: str, source: str = "junit.xml") -> TestRun:
    """Parse JUnit XML text into a TestRun."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise TestHealthError(f"invalid JUnit XML: {exc}") from exc
    suites: list[ET.Element] = []
    if root.tag == "testsuites":
        suites = list(root.iter("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        raise TestHealthError(f"unexpected JUnit root element: {root.tag!r}")
    cases: list[TestCase] = []
    for suite in suites:
        for element in suite.iter("testcase"):
            classname = element.get("classname", "")
            name = element.get("name", "")
            outcome, message = _case_outcome(element)
            try:
                duration = float(element.get("time", "0") or 0)
            except ValueError:
                duration = 0.0
            cases.append(
                TestCase(
                    id=f"{classname}::{name}" if classname else name,
                    classname=classname,
                    name=name,
                    outcome=outcome,
                    duration=duration,
                    message=message,
                )
            )
    return TestRun(source=source, cases=cases)


def run_to_history_entry(run: TestRun) -> dict:
    return {
        "source": run.source,
        "cases": [{"id": case.id, "outcome": case.outcome} for case in run.cases],
    }


def load_history(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise TestHealthError(f"history file is not a JSON list: {path}")
    return data


def append_history(path: str, run: TestRun) -> list[dict]:
    history = load_history(path)
    history.append(run_to_history_entry(run))
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2)
    os.replace(tmp_path, path)
    return history


def detect_flaky(history: list[dict]) -> list[dict]:
    """Return cases with both good and bad outcomes across runs."""
    seen: dict[str, set[str]] = {}
    runs_seen: dict[str, int] = {}
    for entry in history:
        for case in entry.get("cases", []):
            case_id = case.get("id", "")
            outcome = case.get("outcome", "")
            if outcome in GOOD:
                seen.setdefault(case_id, set()).add("good")
            elif outcome in BAD:
                seen.setdefault(case_id, set()).add("bad")
            runs_seen[case_id] = runs_seen.get(case_id, 0) + 1
    flaky = []
    for case_id, buckets in sorted(seen.items()):
        if buckets == {"good", "bad"}:
            flaky.append({"id": case_id, "runs_seen": runs_seen.get(case_id, 0)})
    return flaky
