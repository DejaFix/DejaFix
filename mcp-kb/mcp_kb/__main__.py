"""`python -m mcp_kb` — streamable HTTP :8300/mcp"""

import os

import uvicorn

from mcp_kb.server import build_app


def main() -> None:
    host = os.environ.get("MCP_KB_HOST", "127.0.0.1")  # compose 에서는 0.0.0.0
    port = int(os.environ.get("MCP_KB_PORT", "8300"))
    uvicorn.run(build_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
