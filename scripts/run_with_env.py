"""루트 .env를 python-dotenv로 읽은 뒤(이미 있는 환경 변수가 우선) 서비스를 띄운다. 값은 출력하지 않는다.

    uv run --package <패키지> python scripts/run_with_env.py module <모듈> [인자...]   # python -m <모듈> [인자...]
    uv run --package <패키지> python scripts/run_with_env.py asgi <앱> <포트>         # uvicorn <앱>

Agent·Scheduler·mcp-zabbix는 os.environ만 읽고 .env를 직접 로드하지 않는다(Backend만 pydantic env_file).
`uv run --env-file`은 값에 공백이 있으면 그 줄부터 읽지 않아(#83) 이 런처를 쓴다. scripts/dev-up.ps1이 부른다.
"""

import runpy
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

mode, target = sys.argv[1], sys.argv[2]
if mode == "module":
    sys.argv = [target, *sys.argv[3:]]  # 모듈의 하위 명령 인자(예: dejafix_kb index)
    runpy.run_module(target, run_name="__main__", alter_sys=True)
elif mode == "asgi":
    import uvicorn

    uvicorn.run(target, host="127.0.0.1", port=int(sys.argv[3]))
else:
    raise SystemExit(f"알 수 없는 모드: {mode} (module | asgi)")
