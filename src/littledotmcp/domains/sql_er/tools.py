"""sql_er 域 MCP 工具（M2-06）。

暴露：
- sql_er_from_ddl：解析 DDL -> Mermaid erDiagram（可指定 dialect）。
"""

from __future__ import annotations

from ...common.logging import get_logger
from ...common.result import fail, ok
from ...server import mcp
from .dialect import normalize_dialect
from .parser import ParseError, parse_ddl
from .render import render_er

logger = get_logger(__name__)


@mcp.tool(
    name="sql_er_from_ddl",
    description=(
        "将 Hive/Doris/Oracle/MySQL 的 CREATE TABLE DDL 解析为 Mermaid erDiagram。"
        "支持多表，可指定 dialect 跳过自动检测。"
    ),
)
def sql_er_from_ddl(ddl: str, dialect: str = "") -> dict:
    """DDL -> ER 图工具。"""
    try:
        schema = parse_ddl(ddl, dialect=normalize_dialect(dialect) if dialect else None)
    except ParseError as exc:
        logger.warning("sql_er 解析失败：%s", exc.message)
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("sql_er 未预期错误")
        return fail(message=f"解析失败：{exc}")

    mermaid = render_er(schema)
    logger.info("sql_er 解析成功 dialect=%s 表数=%d", schema.dialect, len(schema.tables))
    return ok(
        data={
            "dialect": schema.dialect,
            "tables": [t.name for t in schema.tables],
            "mermaid": mermaid,
        },
        message=f"已生成 {len(schema.tables)} 张表的 ER 图",
    )
