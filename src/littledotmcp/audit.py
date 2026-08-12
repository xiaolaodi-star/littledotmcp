"""审计日志（M1-06）。

关键操作（svn 提交、知识库变更、需求状态流转等）统一落 svn_ops_log 风格表。
当前通用化：所有带 owner_id 的写操作均可调用 write_audit 记录。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from .common.logging import get_logger
from .db import engine as db_engine
from .db.models import SvnOpLog

logger = get_logger(__name__)


def write_audit(owner_id: str, entity: str, action: str, detail: str = "") -> None:
    """写入审计记录（非 svn 专属，svn 专用走 svn_ops_log）。"""
    try:
        with db_engine.SessionLocal() as session:
            log = SvnOpLog(
                id=uuid.uuid4().hex,
                owner_id=owner_id,
                repo_id=entity,
                op=action,
                message=detail[:2000],
            )
            session.add(log)
            session.commit()
    except Exception as exc:  # 审计失败不应阻断主流程
        logger.warning("审计写入失败 owner=%s action=%s err=%s", owner_id, action, exc)
