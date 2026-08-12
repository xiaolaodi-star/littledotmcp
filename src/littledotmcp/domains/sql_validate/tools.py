"""sql_validate 域 MCP 工具（M2-07）。

暴露：
- sql_validate_script：对 DDL 脚本做 L1 静态校验（保留字/重复/类型/FK/分区）。
  L2 真实库校验经 SqlValidator 插件接入，默认仅 L1。
"""

from __future__ import annotations

from ...common.logging import get_logger
from ...common.result import fail, ok
from ...server import mcp
from ..sql_er.parser import ParseError, parse_ddl
from .adapter import NullSqlValidator, build_report_with_l2

logger = get_logger(__name__)


@mcp.tool(
    name="sql_validate_script",
    description=(
        "校验 SQL DDL 脚本（三方言）：L1 静态规则（重复表/列、保留字、类型、FK 目标、"
        "分区重复）+ L2 真实库适配（可选）。返回分级问题列表。"
    ),
)
def sql_validate_script(ddl: str, dialect: str = "", enable_l2: bool = False) -> dict:
    """SQL 校验工具。"""
    try:
        schema = parse_ddl(ddl, dialect=dialect or None)
    except ParseError as exc:
        logger.warning("sql_validate 解析失败：%s", exc.message)
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("sql_validate 未预期错误")
        return fail(message=f"校验失败：{exc}")

    validator = NullSqlValidator() if not enable_l2 else None
    if enable_l2 and validator is None:
        # L2 插件未提供时退化为 L1，并提示
        logger.info("L2 未配置真实库适配，仅执行 L1")
    report = build_report_with_l2(schema, validator)

    logger.info(
        "sql_validate 完成 dialect=%s errors=%d warnings=%d",
        schema.dialect, len(report.errors), len(report.warnings),
    )
    return ok(
        data=report.as_dict(),
        message="校验通过" if report.passed else f"发现 {len(report.errors)} 个错误",
    )
