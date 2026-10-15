"""One-time setup of the local Docker Zabbix 7.0 server (infra/zabbix/local-server) for DejaFix. Safe to re-run (skips what exists).

- registers this PC as host (active checks, template "Windows by Zabbix agent active") in group "DejaFix/Windows"
- adds Windows event log items (active, log type)
- creates a read-only API role/user group/user + API token for the platform (7 get methods only)
- changes the default Admin password (last step)
Secrets are written only to --secrets (outside the repo), never printed.

usage: python setup_local_server.py --host-name $env:COMPUTERNAME --secrets $HOME\\host-setup\\zabbix-secrets.json
       [--url http://127.0.0.1:18080/api_jsonrpc.php] [--admin-password zabbix]
Never point --url at the team (production) Zabbix: this script writes (hosts, roles, users, tokens).
"""

import argparse
import json
import pathlib
import secrets
import string
import urllib.request

API_METHODS = [
    "host.get",
    "item.get",
    "history.get",
    "trend.get",
    "problem.get",
    "event.get",
    "trigger.get",
]
EVENTLOG_ITEMS = [
    (
        "Windows: System event log (warning/error/critical)",
        'eventlog[System,,"Warning|Error|Critical",,,,skip]',
        2,
    ),
    (
        "Windows: Application event log (error/critical)",
        'eventlog[Application,,"Error|Critical",,,,skip]',
        2,
    ),
    (
        "Windows: System event log error count",
        'eventlog.count[System,,"Error|Critical",,,,skip]',
        3,
    ),
]


class Api:
    def __init__(self, url):
        self.url, self.token, self.n = url, None, 0

    def call(self, method, params, auth=True):
        self.n += 1
        headers = {"Content-Type": "application/json-rpc"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params, "id": self.n}
        ).encode()
        with urllib.request.urlopen(
            urllib.request.Request(self.url, body, headers), timeout=30
        ) as r:
            resp = json.loads(r.read())
        if "error" in resp:
            raise RuntimeError(
                f"{method}: {resp['error'].get('message')} {resp['error'].get('data')}"
            )
        return resp["result"]


def pw(n=24):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n)) + "!a9"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18080/api_jsonrpc.php")
    ap.add_argument("--host-name", required=True)
    ap.add_argument("--secrets", required=True)
    ap.add_argument("--admin-password", default="zabbix")
    a = ap.parse_args()
    sec_path = pathlib.Path(a.secrets)
    store = (
        json.loads(sec_path.read_text(encoding="utf-8")) if sec_path.exists() else {}
    )
    api = Api(a.url)
    print("version", api.call("apiinfo.version", {}, auth=False))
    admin_pw = store.get("admin_password", a.admin_password)
    api.token = api.call(
        "user.login", {"username": "Admin", "password": admin_pw}, auth=False
    )

    # host group + host
    g = api.call(
        "hostgroup.get",
        {"filter": {"name": ["DejaFix/Windows"]}, "output": ["groupid"]},
    )
    groupid = (
        g[0]["groupid"]
        if g
        else api.call("hostgroup.create", {"name": "DejaFix/Windows"})["groupids"][0]
    )
    tpl = api.call(
        "template.get",
        {
            "filter": {"host": ["Windows by Zabbix agent active"]},
            "output": ["templateid"],
        },
    )
    if not tpl:
        raise SystemExit("template 'Windows by Zabbix agent active' not found")
    h = api.call("host.get", {"filter": {"host": [a.host_name]}, "output": ["hostid"]})
    if h:
        hostid = h[0]["hostid"]
        print("host exists", hostid)
    else:
        hostid = api.call(
            "host.create",
            {
                "host": a.host_name,
                "groups": [{"groupid": groupid}],
                "templates": [{"templateid": tpl[0]["templateid"]}],
                "tags": [{"tag": "project", "value": "dejafix"}],
            },
        )["hostids"][0]
        print("host created", hostid)

    # event log items (active, not in the template)
    for name, key, vtype in EVENTLOG_ITEMS:
        if api.call(
            "item.get",
            {"hostids": hostid, "filter": {"key_": [key]}, "output": ["itemid"]},
        ):
            print("item exists", key)
            continue
        api.call(
            "item.create",
            {
                "hostid": hostid,
                "name": name,
                "key_": key,
                "type": 7,
                "value_type": vtype,
                "delay": "1m",
                "history": "7d",
                "tags": [{"tag": "component", "value": "eventlog"}],
            },
        )
        print("item created", key)

    # read-only API access for the platform
    r = api.call(
        "role.get",
        {"filter": {"name": ["DejaFix API read-only"]}, "output": ["roleid"]},
    )
    roleid = (
        r[0]["roleid"]
        if r
        else api.call(
            "role.create",
            {
                "name": "DejaFix API read-only",
                "type": 1,
                "rules": {
                    "ui.default_access": 0,
                    "modules.default_access": 0,
                    "actions.default_access": 0,
                    "api.access": 1,
                    "api.mode": 1,
                    "api": API_METHODS,
                },
            },
        )["roleids"][0]
    )
    ug = api.call(
        "usergroup.get",
        {"filter": {"name": ["DejaFix API readers"]}, "output": ["usrgrpid"]},
    )
    usrgrpid = (
        ug[0]["usrgrpid"]
        if ug
        else api.call(
            "usergroup.create",
            {
                "name": "DejaFix API readers",
                "gui_access": 3,
                "hostgroup_rights": [{"id": groupid, "permission": 2}],
            },
        )["usrgrpids"][0]
    )
    u = api.call(
        "user.get", {"filter": {"username": ["dejafix-api"]}, "output": ["userid"]}
    )
    if u:
        userid = u[0]["userid"]
    else:
        store["api_user_password"] = pw()
        userid = api.call(
            "user.create",
            {
                "username": "dejafix-api",
                "passwd": store["api_user_password"],
                "roleid": roleid,
                "usrgrps": [{"usrgrpid": usrgrpid}],
            },
        )["userids"][0]
    if "api_token" not in store:
        t = api.call(
            "token.get",
            {
                "filter": {"name": ["dejafix-backend"], "userid": userid},
                "output": ["tokenid"],
            },
        )
        tokenid = (
            t[0]["tokenid"]
            if t
            else api.call(
                "token.create", {"name": "dejafix-backend", "userid": userid}
            )["tokenids"][0]
        )
        store["api_token"] = api.call("token.generate", [tokenid])[0]["token"]
    print("api user", userid, "role", roleid, "group", usrgrpid)
    sec_path.write_text(json.dumps(store, indent=1), encoding="utf-8")

    # change default Admin password last
    if "admin_password" not in store:
        new = pw()
        api.call(
            "user.update", {"userid": "1", "current_passwd": admin_pw, "passwd": new}
        )
        store["admin_password"] = new
        sec_path.write_text(json.dumps(store, indent=1), encoding="utf-8")
        api.token = api.call(
            "user.login", {"username": "Admin", "password": new}, auth=False
        )
        print("admin password changed, re-login ok")
    print("secrets saved to", sec_path)


if __name__ == "__main__":
    main()
