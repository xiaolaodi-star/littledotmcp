"""L2 真实库校验适配（M2-05）。

定义 SqlValidator SPI（依赖倒置），真实库（Oracle / Hive / Doris JDBC）实现为可选插件。
默认 NullSqlValidator 空实现不报错，保证无外部依赖时工具可用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..sql_er.model import Schema
from .validator import Issue, ValidationReport


class SqlValidator(ABC):
    """真实库适配接口：在真实库中校验 Schema（如编译/对象存在性）。"""

    @abstractmethod
    def validate_against_db(self, schema: Schema) -> list[Issue]:
        """返回真实库校验发现的问题（error/warning）。"""
        raise NotImplementedError


class NullSqlValidator(SqlValidator):
    """默认空实现：不连接任何真实库，返回空问题列表。"""

    def validate_against_db(self, schema: Schema) -> list[Issue]:
        return []


def build_report_with_l2(schema: Schema, validator: SqlValidator | None = None) -> ValidationReport:
    """组合 L1 + L2 校验。validator 为 None 时退化为仅 L1。"""
    from .validator import validate

    report = validate(schema)
    if validator is not None:
        report.issues.extend(validator.validate_against_db(schema))
    return report
