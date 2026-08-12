"""用户与 Token 鉴权（M1-05）。

- 密码哈希：argon2（抗 GPU，适合个人级）
- 注册/登录：返回 Bearer Token（个人模式复用长期 token；多用户阶段可轮换）
- owner_id：业务实体隔离键即 user.id
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid

from sqlalchemy import select

from .common.errors import AuthError, ValidationError
from .common.logging import get_logger
from .db import engine as db_engine
from .db.models import User

logger = get_logger(__name__)

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    _ph = PasswordHasher()
except ImportError:  # pragma: no cover - 依赖缺失时明确提示
    raise SystemExit("缺少 argon2 依赖，请执行 uv add argon2-cffi")


def register(username: str, password: str, display_name: str = "") -> dict:
    """注册新用户，返回统一信封。"""
    if not username or not password:
        raise ValidationError("用户名与密码必填")
    with db_engine.SessionLocal() as session:
        exists = session.scalar(select(User).where(User.username == username))
        if exists:
            raise ValidationError("用户名已存在")
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            password_hash=_ph.hash(password),
            display_name=display_name or username,
        )
        session.add(user)
        session.commit()
        logger.info("用户注册成功 username=%s", username)
        return {"user_id": user.id, "username": user.username}


def login(username: str, password: str) -> dict:
    """登录并签发 token。"""
    with db_engine.SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user is None or not user.is_active:
            raise AuthError("用户名或密码错误")
        try:
            _ph.verify(user.password_hash, password)
        except VerifyMismatchError:
            raise AuthError("用户名或密码错误")
        # argon2 参数升级
        if _ph.check_needs_rehash(user.password_hash):
            user.password_hash = _ph.hash(password)
        user.token = secrets.token_hex(32)
        session.commit()
        logger.info("用户登录成功 username=%s", username)
        return {"user_id": user.id, "token": user.token}


def authenticate(token: str) -> str:
    """校验 Bearer Token，返回 owner_id（即 user.id）。失败抛 AuthError。"""
    if not token:
        raise AuthError("缺少鉴权 Token")
    with db_engine.SessionLocal() as session:
        user = session.scalar(select(User).where(User.token == token))
        if user is None or not user.is_active:
            raise AuthError("Token 无效或已失效")
        return user.id
