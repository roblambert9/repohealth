import json

import pytest
from fastapi.testclient import TestClient

from repohealth.api import app
from repohealth.cli import main
from repohealth.testhealth import (
    TestHealthError,
    append_history,
    detect_flaky,
    parse_junit_xml,
    run_to_history_entry,
)

SAMPLE_XML = """<testsuites>
  <testsuite name="demo" tests="4">
    <testcase classname="test_demo" name="test_pass" time="0.1"/>
    <testcase classname="test_demo" name="test_fail" time="0.2">
      <failure message="assert 1 == 2">traceback here</failure>
    </testcase>
    <testcase classname="test_demo" name="test_error" time="0.3">
      <error message="boom">traceback here</error>
    </testcase>
    <testcase classname="test_demo" name="test_skip" time="0.0">
      <skipped/>
    </testcase>
  </testsuite>
</testsuites>"""


def test_parse_counts_come_from_cases_not_suite_attributes():
    run = parse_junit_xml(SAMPLE_XML, source="demo.xml")
    assert run.totals == {"passed": 1, "failed": 1, "error": 1, "skipped": 1, "total": 4}
    assert run.has_failures is True
    assert run.duration == pytest.approx(0.6)


def test_parse_invalid_xml_errors():
    with pytest.raises(TestHealthError):
        parse_junit_xml("not xml at all")


def test_flaky_detection_ignores_skips():
    history = [
        {"source": "a", "cases": [
            {"id": "t::flaky", "outcome": "passed"},
            {"id": "t::stable", "outcome": "passed"},
            {"id": "t::skippy", "outcome": "skipped"},
        ]},
        {"source": "b", "cases": [
            {"id": "t::flaky", "outcome": "failed"},
            {"id": "t::stable", "outcome": "passed"},
            {"id": "t::skippy", "outcome": "passed"},
        ]},
    ]
    flaky = detect_flaky(history)
    assert [entry["id"] for entry in flaky] == ["t::flaky"]


def test_history_append_is_atomic_and_grows(tmp_path):
    history_path = tmp_path / "history.json"
    run = parse_junit_xml(SAMPLE_XML, source="demo.xml")
    history = append_history(str(history_path), run)
    assert len(history) == 1
    history = append_history(str(history_path), run)
    assert len(history) == 2
    assert json.loads(history_path.read_text()) == history


def test_cli_test_health_exit_codes(tmp_path):
    xml_path = tmp_path / "junit.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    report_path = tmp_path / "report.md"
    code = main(["test-health", str(xml_path), "--report", str(report_path)])
    assert code == 2  # Failures present.
    report = report_path.read_text()
    assert "failed 1, errors 1" in report

    passing = tmp_path / "passing.xml"
    passing.write_text(
        '<testsuite name="ok"><testcase classname="t" name="test_a" time="0.1"/></testsuite>',
        encoding="utf-8",
    )
    assert main(["test-health", str(passing)]) == 0
    assert main(["test-health", str(tmp_path / "missing.xml")]) == 1


def test_cli_history_flags_flaky(tmp_path):
    xml_path = tmp_path / "junit.xml"
    xml_path.write_text(SAMPLE_XML, encoding="utf-8")
    passing_xml = tmp_path / "passing.xml"
    passing_xml.write_text(
        '<testsuite name="ok">'
        '<testcase classname="test_demo" name="test_fail" time="0.1"/>'
        '<testcase classname="test_demo" name="test_pass" time="0.1"/>'
        "</testsuite>",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.json"
    report_path = tmp_path / "report.md"
    main(["test-health", str(xml_path), "--history", str(history_path)])
    main(["test-health", str(passing_xml), "--history", str(history_path),
          "--report", str(report_path)])
    report = report_path.read_text()
    assert "Flaky cases (across 2 runs)" in report
    assert "test_demo::test_fail" in report


def test_api_test_health():
    client = TestClient(app)
    response = client.post("/test-health", json={"junit_xml": SAMPLE_XML})
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["failed"] == 1
    assert len(body["failures"]) == 2
    bad = client.post("/test-health", json={"junit_xml": "nope"})
    assert bad.status_code == 400
