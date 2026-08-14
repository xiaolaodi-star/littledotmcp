"""规范模板注入（M5-04）。

环境变量 STANDARD_TEMPLATES=1 时执行，否则直接跳过（幂等）：
向 standards 表写入命名/SQL/提交/上线清单四份内置模板，
已存在的 name 不覆盖，可重复执行。
"""

from __future__ import annotations

import os
import uuid

from littledotmcp.common.logging import get_logger
from littledotmcp.db import engine as db_engine
from littledotmcp.db import models  # noqa: F401 确保模型注册
from littledotmcp.db.models import Standard

logger = get_logger(__name__)

DEFAULT_OWNER = "local"

TEMPLATES: list[tuple[str, str, str]] = [
    (
        "命名规范",
        "naming",
        """# 命名规范

## 通用
- 标识符使用小驼峰（Python）/大驼峰（Java）/kebab-case（URL）。
- 禁止拼音缩写、含义不明的单字母（循环变量除外）。

## 数据库
- 表名：小写蛇形复数，如 `user_accounts`。
- 字段：小写蛇形，如 `created_at`。
- 主键统一 `id`（bigint 自增或 UUID）。

## 接口
- REST 资源用名词复数：`GET /api/v1/orders`。
- 错误码三段式：`ERR_MODULE_CODE`。
""",
    ),
    (
        "SQL 编写规范",
        "sql",
        """# SQL 编写规范

## 强制
- 所有查询必须带 `WHERE` 或明确全表意图，禁止无过滤 SELECT。
- 禁止 `SELECT *`，显式列出字段。
- 绑定参数代替字符串拼接，防注入。

## 建议
- 复杂 SQL 用 CTE 分步，控制单条长度。
- DDL 变更走迁移脚本，不直连生产库。
""",
    ),
    (
        "代码提交规范",
        "git",
        """# 代码提交规范

## 格式
`type(scope): subject`，如 `feat(req): 支持需求状态流转`。

## type
- feat / fix / docs / style / refactor / perf / test / chore

## 要求
- 单次提交只做一件事；关联需求写 `Refs: REQ-xxx`。
- 提交信息用中文说明做什么、为何做。
""",
    ),
    (
        "上线检查清单",
        "release",
        """# 上线检查清单

- [ ] 本地测试通过（pytest 全绿）
- [ ] 数据库迁移脚本已执行且可回滚
- [ ] 配置项经 .env 注入，无硬编码密钥
- [ ] 日志脱敏检查（token/secret 不落盘）
- [ ] 灰度/回滚方案就绪
- [ ] 监控与告警已配置
""",
    ),
]


def seed_standards(force: bool = False) -> int:
    """注入内置模板，返回新增条数（已存在不覆盖）。"""
    added = 0
    with db_engine.SessionLocal() as session:
        for name, category, content in TEMPLATES:
            exists = (
                session.query(Standard)
                .filter(Standard.owner_id == DEFAULT_OWNER, Standard.name == name)
                .first()
            )
            if exists is not None and not force:
                continue
            if exists is not None:
                exists.content = content
                exists.category = category
            else:
                session.add(
                    Standard(
                        id=uuid.uuid4().hex,
                        owner_id=DEFAULT_OWNER,
                        name=name,
                        category=category,
                        content=content,
                    )
                )
            added += 1
        session.commit()
    logger.info("seed_standards 完成 added=%d force=%s", added, force)
    return added


def main() -> None:
    if os.environ.get("STANDARD_TEMPLATES") != "1":
        print("STANDARD_TEMPLATES != 1，跳过模板注入（设置 STANDARD_TEMPLATES=1 开启）")
        return
    n = seed_standards()
    print(f"规范模板注入完成：{n} 条（已存在跳过）")


if __name__ == "__main__":
    main()
