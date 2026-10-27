from fastapi.testclient import TestClient

from repohealth.api import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scan_with_stub_map(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    response = client.post("/scan", json={
        "target": str(tmp_path),
        "stub_map": {"requests": "Apache-2.0"},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "PASS"
    assert body["sbom"]["components"][0]["licenses"] == [{"license": {"id": "Apache-2.0"}}]
    assert "Verdict: PASS" in body["report_markdown"]


def test_scan_missing_target_is_400():
    response = client.post("/scan", json={"target": "/definitely/not/here"})
    assert response.status_code == 400
