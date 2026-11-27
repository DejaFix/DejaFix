import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "docker" / "app-healthcheck.py"
_spec = importlib.util.spec_from_file_location("app_healthcheck", _PATH)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)


def _serve(status: int, body: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def serve():
    servers = []

    def _start(status, body):
        s = _serve(status, body)
        servers.append(s)
        return f"http://127.0.0.1:{s.server_port}/healthz"

    yield _start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_mcp_zabbix_ok(serve):
    assert hc.check_mcp_zabbix(serve(200, json.dumps({"ok": True}).encode()), 2)


def test_mcp_zabbix_zabbix_down_passes(serve):
    body = json.dumps({"ok": True, "zabbix": "down"}).encode()
    assert hc.check_mcp_zabbix(serve(200, body), 2)


def test_mcp_zabbix_ok_false_fails(serve):
    assert not hc.check_mcp_zabbix(serve(200, b'{"ok": false}'), 2)


def test_mcp_zabbix_non_200_fails(serve):
    assert not hc.check_mcp_zabbix(serve(503, b'{"ok": true}'), 2)


def test_mcp_zabbix_no_response_fails():
    # 포트에 아무도 듣지 않는 경우
    s = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = s.server_port
    s.server_close()
    assert not hc.check_mcp_zabbix(f"http://127.0.0.1:{port}/healthz", 1)


def test_main_zabbix_down_still_healthy(monkeypatch):
    monkeypatch.setattr(hc, "check_http", lambda url: True)
    monkeypatch.setattr(hc, "check_mcp_zabbix", lambda: True)
    monkeypatch.setattr(hc, "check_scheduler", lambda: True)
    assert hc.main() == 0


def test_main_reports_mcp_zabbix_failure(monkeypatch, capsys):
    monkeypatch.setattr(hc, "check_http", lambda url: True)
    monkeypatch.setattr(hc, "check_mcp_zabbix", lambda: False)
    monkeypatch.setattr(hc, "check_scheduler", lambda: True)
    assert hc.main() == 1
    assert "mcp-zabbix" in capsys.readouterr().err


def test_backend_agent_checks_unchanged(monkeypatch):
    assert set(hc.HTTP_CHECKS) == {"backend", "agent"}
