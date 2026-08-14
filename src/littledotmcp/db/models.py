"""数据模型 v1（M1-02）。

14 张核心表，用户数据表全部带 owner_id 实现多租户隔离：
users, kb_documents, kb_chunks, documents, svn_repos, svn_ops_log,
projects, milestones, tasks, requirements, tags, entity_tags, mindmaps, standards
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """声明基类。"""


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # "admin" / "user"（M11 管理端）
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))
    token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # owner_id 自引用（知识归属即本人）
    @property
    def owner_id(self) -> str:
        return self.id


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32), default="local")  # local/wecom
    storage_key: Mapped[str] = mapped_column(String(512))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.now(dt.timezone.utc), onupdate=dt.datetime.now(dt.timezone.utc)
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(32), default="LOCAL")  # LOCAL/WECOM
    storage_key: Mapped[str] = mapped_column(String(512))
    size: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


class SvnRepo(Base):
    __tablename__ = "svn_repos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(512))
    username: Mapped[str] = mapped_column(String(128), default="")
    cred_enc: Mapped[str] = mapped_column(String(512), default="")  # 加密后的口令
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


class SvnOpLog(Base):
    __tablename__ = "svn_ops_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    repo_id: Mapped[str] = mapped_column(String(64), index=True)
    op: Mapped[str] = mapped_column(String(32))
    rev: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    requirement_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # M8 追溯链路
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    due: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="todo")  # todo/doing/done
    weight: Mapped[int] = mapped_column(Integer, default=1)


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    # DRAFT->ASSESS->DEV->ONLINE->DONE / CLOSED
    detail: Mapped[str] = mapped_column(Text, default="")
    related_commit: Mapped[str] = mapped_column(String(255), default="")
    related_doc: Mapped[str] = mapped_column(String(255), default="")
    related_tag: Mapped[str] = mapped_column(String(255), default="")  # M8 标签关联（逗号分隔 tag_id）
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # M8 扩展 B
    milestone_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # M8 扩展 B
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.now(dt.timezone.utc), onupdate=dt.datetime.now(dt.timezone.utc)
    )

    __table_args__ = (UniqueConstraint("owner_id", "code", name="uq_req_owner_code"),)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    color: Mapped[str] = mapped_column(String(16), default="#888888")

    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_tag_owner_name"),)


class EntityTag(Base):
    __tablename__ = "entity_tags"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # requirement/project/task/doc/...
    entity_id: Mapped[str] = mapped_column(String(64), index=True)


class Mindmap(Base):
    __tablename__ = "mindmaps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    mermaid: Mapped[str] = mapped_column(Text, default="")
    opml: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


class Standard(Base):
    __tablename__ = "standards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now(dt.timezone.utc))


# ===== M11 管理端新增模型 =====


class UserSession(Base):
    """管理端登录态（独立于 users.token，避免顶掉 MCP 用户 Bearer Token）。"""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.now(dt.timezone.utc)
    )


class CallError(Base):
    """MCP 工具调用异常记录（管理端异常采集数据底座）。"""

    __tablename__ = "call_errors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    args_summary: Mapped[str] = mapped_column(Text, default="")  # 脱敏后的参数摘要
    error_type: Mapped[str] = mapped_column(String(128), default="")
    error_msg: Mapped[str] = mapped_column(Text, default="")
    trace_head: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open/closed
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.now(dt.timezone.utc)
    )


class AuditLog(Base):
    """管理端操作留痕（与 svn_ops_log 并存）。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.now(dt.timezone.utc)
    )
