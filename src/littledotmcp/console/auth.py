"""M11-02 管理端会话鉴权（独立于 MCP Bearer Token）。

设计要点：
- 管理端登录态存于独立 `user_sessions` 表，**绝不调用会重签 `users.token` 的 auth.login**，
  避免顶掉 MCP 用户的 Bearer Token（现状隐患）。
- 密码校验复用 auth.py 的 argon2 `_ph`（同一依赖，零新增）。
- 空库（`users` 为空）时开放"创建首个管理员"：`bootstrap_admin` 既支持一次性环境变量
  `ADMIN_BOOTSTRAP_USER/PASSWORD`，也可在 `/admin/api/setup` 由浏览器表单创建。
- Session 默认 12h 过期；Cookie 由 ConsoleAuth 中间件 HttpOnly + SameSite=Strict 下发。
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import uuid

from sqlalchemy import select

from ..auth import _ph  # 复用 argon2 实例（同一依赖）
from ..common.errors import AuthError, ValidationError
from ..common.logging import get_logger
from ..db import engine as db_engine
from ..db.models import AuditLog, User, UserSession

logger = get_logger(__name__)

SESSION_EXPIRE_HOURS: int = int(os.environ.get("ADMIN_SESSION_HOURS", "12"))
_SESSION_COOKIE: str = "littledot_session"


def _now() -> dt.datetime:
    """当前 UTC 时间（naive，统一无时区存储，避免 SQLite 往返 tz 丢失导致比较错误）。"""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _expires() -> dt.datetime:
    return _now() + dt.timedelta(hours=SESSION_EXPIRE_HOURS)


def create_user(username: str, password: str, role: str = "user", display_name: str = "") -> dict:
    """创建用户（管理员引导/管理端新建）。返回统一信封。"""
    if not username or not password:
        raise ValidationError("用户名与密码必填")
    if role not in ("admin", "user"):
        raise ValidationError("角色非法")
    with db_engine.SessionLocal() as session:
        exists = session.scalar(select(User).where(User.username == username))
        if exists:
            raise ValidationError("用户名已存在")
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            password_hash=_ph.hash(password),
            display_name=display_name or username,
            role=role,
        )
        session.add(user)
        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                actor_id="bootstrap" if role == "admin" else "system",
                action="create_user",
                entity="users",
                entity_id=user.id,
                detail=f"username={username}; role={role}",
            )
        )
        session.commit()
        logger.info("管理端创建用户 username=%s role=%s", username, role)
        return {"user_id": user.id, "username": user.username, "role": user.role}


def authenticate_user(username: str, password: str) -> User:
    """argon2 校验用户名/密码，返回 User；失败抛 AuthError。"""
    with db_engine.SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None or not user.is_active:
            raise AuthError("用户名或密码错误")
        try:
            _ph.verify(user.password_hash, password)
        except Exception:
            raise AuthError("用户名或密码错误")
        if _ph.check_needs_rehash(user.password_hash):
            user.password_hash = _ph.hash(password)
            session.commit()
        # 返回 detached 副本（避免跨 session 使用）
        return User(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            role=user.role,
        )


def create_session(user: User, ip: str = "") -> str:
    """为用户写入 user_sessions，返回 session token。"""
    token = secrets.token_hex(32)
    with db_engine.SessionLocal() as session:
        # 清理该用户过期会话（轻量维护）
        expired = session.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id, UserSession.expires_at < _now()
            )
        ).all()
        for old in expired:
            session.delete(old)
        session.add(
            UserSession(
                id=uuid.uuid4().hex,
                user_id=user.id,
                token=token,
                expires_at=_expires(),
                ip=ip,
            )
        )
        session.commit()
    logger.info("管理端登录成功 username=%s", user.username)
    return token


def get_user_from_session(token: str | None) -> User | None:
    """校验 session token，返回有效 User（已过期/无效返回 None）。"""
    if not token:
        return None
    with db_engine.SessionLocal() as session:
        us = session.scalar(select(UserSession).where(UserSession.token == token))
        if us is None or us.expires_at < _now():
            return None
        user = session.get(User, us.user_id)
        if user is None or not user.is_active:
            return None
        return User(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            role=user.role,
        )


def destroy_session(token: str | None) -> None:
    """登出：删除会话记录。"""
    if not token:
        return
    with db_engine.SessionLocal() as session:
        us = session.scalar(select(UserSession).where(UserSession.token == token))
        if us is not None:
            session.delete(us)
            session.commit()


def count_users() -> int:
    """当前用户总数（判断空库以开放初始化）。"""
    with db_engine.SessionLocal() as session:
        return int(session.scalar(select(__import__("sqlalchemy").func.count()).select_from(User)) or 0)


def is_empty_db() -> bool:
    """users 表是否为空（空库才允许 setup 创建首个管理员）。"""
    return count_users() == 0


def bootstrap_admin() -> dict | None:
    """空库时尝试用一次性环境变量创建管理员。

    返回创建结果或 None（无环境变量 / 非空库 / 已存在）。启动期调用，失败仅告警不阻断。
    """
    user = os.environ.get("ADMIN_BOOTSTRAP_USER")
    pwd = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not user or not pwd:
        return None
    if not is_empty_db():
        logger.info("ADMIN_BOOTSTRAP 跳过：库非空")
        return None
    try:
        return create_user(user, pwd, role="admin")
    except ValidationError as exc:
        logger.warning("ADMIN_BOOTSTRAP 创建失败：%s", exc)
        return None


def session_cookie_name() -> str:
    return _SESSION_COOKIE
