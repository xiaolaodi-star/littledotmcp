"""命令行入口：python -m littledotmcp。

组装 FastMCP 并据 MCP_TRANSPORT 启动 stdio / streamable-http。

注意：MCP stdio 传输要求 stdout 为 UTF-8。Windows 控制台默认 GBK，
须在导入任何库前重绑 stdout/stderr 为 UTF-8，否则 protocol 读写乱码。
"""

from __future__ import annotations

import io
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
else:  # pragma: no cover - 仅极老解释器
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from .server import register_tools, run


def main() -> int:
    register_tools()
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
