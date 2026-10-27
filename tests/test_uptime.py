import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from repohealth.api import app
from repohealth.cli import main
from repohealth.uptime import DOWN, UP, append_log, check_url, load_targets, summarize


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        elif self.path == "/boom":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_check_url_up_down_and_refused(server):
    ok = check_url("ok", f"{server}/ok")
    assert ok.status == UP
    assert ok.http_status == 200
    assert ok.latency_ms >= 0

    boom = check_url("boom", f"{server}/boom")
    assert boom.status == DOWN
    assert boom.http_status == 500

    missing = check_url("missing", f"{server}/nope")
    assert missing.status == DOWN  # 404 is a misbehaving service, not an up one.

    refused = check_url("refused", "http://127.0.0.1:1/")
    assert refused.status == DOWN
    assert refused.http_status is None
    assert refused.error != ""


def test_load_targets_forms(tmp_path):
    config = tmp_path / "targets.json"
    config.write_text(json.dumps(["http://example.com", {"name": "api", "url": "http://api.example.com"}]))
    targets = load_targets(str(config))
    assert targets == [("http://example.com", "http://example.com"), ("api", "http://api.example.com")]


def test_summarize_percentages():
    log = [
        {"name": "a", "url": "http://a", "status": UP, "checked_at": "t1"},
        {"name": "a", "url": "http://a", "status": DOWN, "checked_at": "t2"},
        {"name": "a", "url": "http://a", "status": UP, "checked_at": "t3"},
    ]
    summary = summarize(log)
    assert summary["a"]["checks"] == 3
    assert summary["a"]["uptime_pct"] == pytest.approx(66.7, abs=0.05)
    assert summary["a"]["last_status"] == UP


def test_log_append_is_atomic_and_grows(tmp_path, server):
    log_path = tmp_path / "uptime.json"
    results = [check_url("ok", f"{server}/ok")]
    log = append_log(str(log_path), results)
    assert len(log) == 1
    log = append_log(str(log_path), results)
    assert len(log) == 2
    assert json.loads(log_path.read_text()) == log


def test_cli_uptime_exit_codes(tmp_path, server):
    report_path = tmp_path / "report.md"
    code = main(["uptime", f"{server}/ok", "--report", str(report_path)])
    assert code == 0
    assert "1 up, 0 down" in report_path.read_text()
    code = main(["uptime", f"{server}/ok", f"{server}/boom"])
    assert code == 2
    assert main(["uptime"]) == 1


def test_api_uptime(server):
    client = TestClient(app)
    response = client.post("/uptime", json={"targets": [{"url": f"{server}/ok"}]})
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["status"] == UP
    assert "1 up, 0 down" in body["report_markdown"]
