"""dejafix-app 헬스체크 4개: backend·agent·mcp-zabbix 의 /healthz 와 scheduler 프로세스(supervisorctl).

하나라도 실패하면 종료 코드 1. 실패한 항목 이름만 stderr 로 낸다(비밀값 없음).
"""

import subprocess
import sys
import urllib.request

HTTP_CHECKS = {
    "backend": "http://127.0.0.1:8000/healthz",
    "agent": "http://127.0.0.1:8100/healthz",
    "mcp-zabbix": "http://127.0.0.1:8200/healthz",
}


def check_http(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_scheduler() -> bool:
    # scheduler 는 HTTP 포트가 없다. supervisord 가 RUNNING 으로 보는지 확인.
    try:
        out = subprocess.run(
            ["supervisorctl", "-c", "/etc/supervisord.conf", "status", "scheduler"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:
        return False
    return "RUNNING" in out


def main() -> int:
    failed = [name for name, url in HTTP_CHECKS.items() if not check_http(url)]
    if not check_scheduler():
        failed.append("scheduler")
    if failed:
        print("unhealthy: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
