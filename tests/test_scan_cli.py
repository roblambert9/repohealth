import json

from repohealth.cli import main


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_cli_pass(tmp_path):
    _write(tmp_path, "requirements.txt", "requests==2.31.0\nflask==3.0.0\n")
    stub = _write(tmp_path, "stub.json", json.dumps({"requests": "Apache-2.0", "flask": "BSD-3-Clause"}))
    sbom_path = tmp_path / "sbom.json"
    report_path = tmp_path / "report.md"
    code = main(["scan", str(tmp_path), "--stub-map", str(stub),
                 "--sbom", str(sbom_path), "--report", str(report_path)])
    assert code == 0
    sbom = json.loads(sbom_path.read_text())
    assert len(sbom["components"]) == 2
    assert "Verdict: PASS" in report_path.read_text()


def test_cli_denied_policy_fails(tmp_path):
    _write(tmp_path, "requirements.txt", "ansible-core==2.16.0\n")
    stub = _write(tmp_path, "stub.json", json.dumps({"ansible-core": "GPL-3.0-only"}))
    policy = _write(tmp_path, "policy.json", json.dumps({"denied": ["GPL-3.0-only"]}))
    report_path = tmp_path / "report.md"
    code = main(["scan", str(tmp_path), "--stub-map", str(stub),
                 "--policy", str(policy), "--report", str(report_path)])
    assert code == 3
    assert "Verdict: FAIL" in report_path.read_text()


def test_cli_unknown_reviews(tmp_path):
    _write(tmp_path, "requirements.txt", "something-obscure==1.0\n")
    stub = _write(tmp_path, "stub.json", json.dumps({}))
    report_path = tmp_path / "report.md"
    code = main(["scan", str(tmp_path), "--stub-map", str(stub), "--report", str(report_path)])
    assert code == 2
    assert "Verdict: REVIEW" in report_path.read_text()


def test_cli_missing_target_errors(tmp_path):
    code = main(["scan", str(tmp_path / "nope")])
    assert code == 1
