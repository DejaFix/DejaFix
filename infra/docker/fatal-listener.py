"""supervisord eventlistener: 4프로세스 중 하나라도 FATAL 이 되면 supervisord 를 종료시켜 컨테이너를 끝낸다.

autorestart 로 여러 번 재시도한 끝에(startretries) FATAL 이 된 경우에만 동작한다.
컨테이너가 끝나면 compose 의 restart: unless-stopped 가 컨테이너 전체를 다시 띄운다.
"""

import os
import signal
import sys

from supervisor import childutils


def main() -> None:
    while True:
        headers, payload = childutils.listener.wait(sys.stdin, sys.stdout)
        if headers.get("eventname") == "PROCESS_STATE_FATAL":
            name = childutils.get_headers(payload).get("processname", "?")
            sys.stderr.write(
                f"fatal-listener: {name} FATAL -> supervisord 종료(컨테이너 재시작)\n"
            )
            sys.stderr.flush()
            os.kill(os.getppid(), signal.SIGTERM)
        childutils.listener.ok(sys.stdout)


if __name__ == "__main__":
    main()
