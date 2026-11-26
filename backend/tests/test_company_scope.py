"""회사 나누기 (결정 019, contracts/api.md 1장 "회사").

누비투어(c-cf2f0d) 요청에 캣북스 장애가 0건이고, 캣북스는 그대로이며, 사람 계정은 머리로 회사를 바꾸지 못한다.
"""

import sqlite3

import pytest
import zabbix_ro

from dejafix_backend.routers import zabbix_settings as zs

NUBI = "c-cf2f0d"
CB = "catbooks"


def scope_shared(path):
    """Scheduler 019 이관을 흉내 낸다: incidents·scheduler_jobs 에 회사 칸, 캣북스 시드 + 누비투어 1건."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=OFF")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(incidents)")]
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='incidents'"
    ).fetchone()[0]
    ddl = ddl.replace("CREATE TABLE incidents (", "CREATE TABLE incidents__new (", 1)
    ddl = ddl.replace("NOT NULL UNIQUE", "NOT NULL")
    ddl = ddl.rstrip().rstrip(")") + (
        ", company_id TEXT NOT NULL, zabbix_conn_id TEXT NOT NULL, resolved_reason TEXT,"
        " UNIQUE (company_id, zabbix_conn_id, zabbix_eventid))"
    )
    conn.execute(ddl)
    names = ", ".join(cols)
    conn.execute(
        f"INSERT INTO incidents__new ({names}, company_id, zabbix_conn_id) "
        f"SELECT {names}, ?, 'env' FROM incidents",
        (CB,),
    )
    conn.execute("DROP TABLE incidents")
    conn.execute("ALTER TABLE incidents__new RENAME TO incidents")
    conn.execute(
        "INSERT INTO incidents (zabbix_eventid, zabbix_triggerid, title, severity, status,"
        " started_at, first_seen_at, last_seen_at, company_id, zabbix_conn_id)"
        " VALUES ('30001', 't9', 'nubi only', 4, 'problem', '2026-11-26T00:00:00Z',"
        " '2026-11-26T00:00:00Z', '2026-11-26T00:00:00Z', ?, 'zc_000000000001')",
        (NUBI,),
    )
    conn.execute("DROP TABLE scheduler_jobs")
    conn.execute(
        "CREATE TABLE scheduler_jobs (company_id TEXT NOT NULL, job TEXT NOT NULL,"
        " last_run_at TEXT, last_ok_at TEXT, status TEXT, message TEXT,"
        " PRIMARY KEY (company_id, job))"
    )
    conn.execute(
        "INSERT INTO scheduler_jobs VALUES (?, 'poll_problems', '2026-11-26T00:00:00Z',"
        " '2026-11-26T00:00:00Z', 'ok', NULL)",
        (CB,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def app(make_client, helpers, env, tmp_path):
    def make(scoped=True, **extra):
        client = make_client(
            seeded=True,
            default_company_id=CB,
            company_header_accounts="admin",
            zabbix_connection_file=str(tmp_path / "zbx.json"),
            **extra,
        )
        if scoped:
            scope_shared(env.shared)
        admin = helpers.login(client, "admin", helpers.admin_password)
        oncall = helpers.login(client, "oncall", helpers.oncall_password)
        return client, admin, oncall

    return make


def _titles(res):
    return {i["title"] for i in res.json()["data"]}


def test_nubi_sees_no_catbooks_incidents(app):
    client, admin, _ = app()
    nubi = {**admin, "X-AX-Company": NUBI}
    res = client.get("/api/incidents", headers=nubi)
    assert res.status_code == 200, res.text
    assert _titles(res) == {"nubi only"}
    assert res.headers["X-DejaFix-Company"] == NUBI
    cb = client.get("/api/incidents", headers=admin)
    assert (
        "nubi only" not in _titles(cb) and len(cb.json()["data"]) == 6
    )  # 캣북스 그대로
    assert cb.headers["X-DejaFix-Company"] == CB


def test_other_company_incident_id_is_404(app):
    client, admin, _ = app()
    cb_id = client.get("/api/incidents", headers=admin).json()["data"][0]["id"]
    res = client.get(f"/api/incidents/{cb_id}", headers={**admin, "X-AX-Company": NUBI})
    assert res.status_code == 404
    assert client.get(f"/api/incidents/{cb_id}", headers=admin).status_code == 200


def test_nubi_detail_has_no_mail_logs(app):
    client, admin, _ = app()
    nubi = {**admin, "X-AX-Company": NUBI}
    nubi_id = client.get("/api/incidents", headers=nubi).json()["data"][0]["id"]
    res = client.get(f"/api/incidents/{nubi_id}", headers=nubi)
    assert res.status_code == 200 and res.json()["data"]["mail_logs"] == []


def test_human_account_cannot_switch_company_by_header(app):
    client, _, oncall = app()
    res = client.get("/api/incidents", headers={**oncall, "X-AX-Company": NUBI})
    assert res.status_code == 403
    assert client.get("/api/incidents", headers=oncall).status_code == 200


def test_bad_header_is_422(app):
    client, admin, _ = app()
    res = client.get("/api/incidents", headers={**admin, "X-AX-Company": "Bad Co!"})
    assert res.status_code == 422


def test_nubi_without_zabbix_is_empty_not_catbooks(app):
    client, admin, _ = app()
    nubi = {**admin, "X-AX-Company": NUBI}
    assert client.get("/api/problems", headers=nubi).json()["data"] == []
    assert client.get("/api/hosts", headers=nubi).json()["data"] == []
    health = client.get("/api/health", headers=nubi).json()["data"]
    assert health["zabbix"] == "none" and health["scheduler_last_ok"] is None
    summary = client.get("/api/dashboard/summary", headers=nubi).json()["data"]
    assert summary["active_incidents"]["value"] == 1
    assert summary["hosts"]["total"]["unknown_reason"] == "NOT_COLLECTED"
    cb_health = client.get("/api/health", headers=admin).json()["data"]
    assert cb_health["zabbix"] == "ok" and cb_health["scheduler_last_ok"] is not None


def test_before_scheduler_migration_reads_are_503(app):
    client, admin, _ = app(scoped=False)
    res = client.get("/api/incidents", headers={**admin, "X-AX-Company": NUBI})
    assert res.status_code == 503


def test_scoping_off_ignores_header_and_sends_no_echo(make_client, helpers):
    client = make_client(seeded=True, company_header_accounts="admin")
    admin = helpers.login(client, "admin", helpers.admin_password)
    res = client.get("/api/incidents", headers={**admin, "X-AX-Company": NUBI})
    assert res.status_code == 200 and len(res.json()["data"]) == 6
    assert "X-DejaFix-Company" not in res.headers


def test_zabbix_settings_are_per_company(app, monkeypatch, tmp_path):
    client, admin, _ = app()
    monkeypatch.setattr(zs, "_resolve", lambda host: ["8.8.8.8"])
    monkeypatch.setattr(zs, "_check", lambda url, token, verify: None)
    nubi = {**admin, "X-AX-Company": NUBI}
    assert (
        client.get("/api/settings/zabbix", headers=nubi).json()["data"]["source"]
        == "none"
    )
    cb_url = "https://cb.example.com/api_jsonrpc.php"
    nubi_url = "https://nubi.example.com/api_jsonrpc.php"
    assert (
        client.put(
            "/api/settings/zabbix", json={"url": cb_url, "token": "cb-t"}, headers=admin
        ).status_code
        == 200
    )
    res = client.put(
        "/api/settings/zabbix", json={"url": nubi_url, "token": "nb-t"}, headers=nubi
    )
    assert res.status_code == 200, res.text
    assert res.headers["X-DejaFix-Company"] == NUBI
    assert (
        client.get("/api/settings/zabbix", headers=nubi).json()["data"]["url"]
        == nubi_url
    )
    assert (
        client.get("/api/settings/zabbix", headers=admin).json()["data"]["url"]
        == cb_url
    )
    path = tmp_path / "zbx.json"
    assert zabbix_ro.read_connection(path, NUBI, CB)["token"] == "nb-t"
    assert zabbix_ro.read_connection(path, CB, CB)["token"] == "cb-t"


@pytest.mark.parametrize(
    "address", ["10.0.0.5", "192.168.0.217", "169.254.169.254", "100.64.0.1"]
)
def test_other_company_cannot_point_at_internal_network(app, monkeypatch, address):
    client, admin, _ = app()
    monkeypatch.setattr(zs, "_resolve", lambda host: [address])
    monkeypatch.setattr(zs, "_check", lambda url, token, verify: None)
    body = {"url": "https://zbx.internal/api_jsonrpc.php", "token": "t"}
    res = client.put(
        "/api/settings/zabbix", json=body, headers={**admin, "X-AX-Company": NUBI}
    )
    assert res.status_code == 422
    if address.startswith(
        ("10.", "192.168.")
    ):  # 기본 회사(설치 주인)는 사내 Zabbix 그대로
        assert (
            client.put("/api/settings/zabbix", json=body, headers=admin).status_code
            == 200
        )
