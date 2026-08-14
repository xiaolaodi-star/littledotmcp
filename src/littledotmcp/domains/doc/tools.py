"""doc 域 MCP 工具（M3-04）：doc_save/read/search/list/delete。

- provider 支持 LOCAL（默认）与 WECOM（M9 企微后端骨架）
- 元数据落 documents 表，经 OwnerScopedRepository 强制 owner 隔离
- LOCAL 原文落 LocalDocStorage（storage_root/owner_id/storage_key）
- WECOM 原文存于企微侧，storage_key 语义为企微 docid
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger
from ...common.result import fail, ok
from ...config import get_settings
from ...db import engine as db_engine
from ...db.models import Document
from ...db.repository import OwnerScopedRepository
from ...rag.parsers import ParseError, parse_document
from ...server import mcp
from .storage import DEFAULT_SIZE_LIMIT, LocalDocStorage
from .wecom import WeComDocClient, build_wecom_client

logger = get_logger(__name__)

_VALID_PROVIDERS = {"LOCAL", "WECOM"}

# stdio 单人模式固定归属；http 多用户模式（M6）按鉴权上下文解析
_DEFAULT_OWNER = "local"

# 列表/搜索分页上限
_MAX_LIMIT = 100

# 扩展名 → MIME（与 rag.parsers 对齐 + 通用类型）
_EXT_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".csv": "text/csv",
    ".html": "text/html",
}


class DocumentRepository(OwnerScopedRepository[Document]):
    """documents 表隔离仓库：全部查询强制 owner_id。"""

    model = Document

    def search_by_owner(
        self,
        owner_id: str,
        *,
        name: str = "",
        mime: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[Document]:
        """按 name 模糊 + mime 精确过滤，时间倒序分页。"""
        stmt = select(Document).where(Document.owner_id == owner_id)
        if name:
            stmt = stmt.where(Document.name.like(f"%{name}%"))
        if mime:
            stmt = stmt.where(Document.mime == mime)
        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())


def _current_owner() -> str:
    """返回当前调用方 owner_id。

    stdio 单人模式固定为 local；http 模式（M6）改为按请求鉴权上下文解析。
    """
    return _DEFAULT_OWNER


def _storage() -> LocalDocStorage:
    """延迟创建存储实例（随配置实时，便于测试重定向）。"""
    return LocalDocStorage(get_settings().storage_root)


def _infer_mime(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return _EXT_MIME.get(suffix, "application/octet-stream")


def _doc_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "name": doc.name,
        "mime": doc.mime,
        "size": doc.size,
        "provider": doc.provider,
        "created_at": doc.created_at.isoformat(),
    }


@mcp.tool(
    name="doc_save",
    description=(
        "保存文档：content 传文本内容，或 path 传本地文件路径（原文整体存储）。"
        "provider=LOCAL（默认）存本地；provider=WECOM 存企微侧（M9 骨架）。"
        "落 documents 表元数据并返回文档 id。"
    ),
)
def doc_save(
    name: str,
    content: str = "",
    path: str = "",
    mime: str = "",
    provider: str = "LOCAL",
) -> dict:
    """保存文档（content 与 path 二选一）。"""
    owner = _current_owner()
    try:
        provider = (provider or "LOCAL").strip().upper()
        if provider not in _VALID_PROVIDERS:
            return fail(message=f"不支持的 provider：{provider}")
        if not name.strip():
            return fail(message="文档名必填")
        if bool(content) == bool(path):
            return fail(message="content 与 path 必须且只能提供一个")

        if path:
            src = Path(path)
            try:
                raw = src.read_bytes()
            except OSError as exc:
                return fail(message=f"读取文件失败：{exc}")
            try:
                parsed = parse_document(src)
                effective_mime = mime or parsed.mime
            except ParseError as exc:
                logger.warning("doc_save 路径解析失败（按原文保存）：%s", exc.message)
                effective_mime = mime or _infer_mime(name)
        else:
            raw = content.encode("utf-8")
            effective_mime = mime or _infer_mime(name)

        if provider == "WECOM":
            return _save_wecom(owner, name, raw, effective_mime)
        # LOCAL：原文落本地存储，storage_key 为 UUID
        storage_key = _storage().save(owner, raw, size_limit=DEFAULT_SIZE_LIMIT)
        with db_engine.SessionLocal() as session:
            repo = DocumentRepository(session)
            doc = Document(
                id=uuid.uuid4().hex,
                owner_id=owner,
                name=name.strip(),
                provider="LOCAL",
                storage_key=storage_key,
                size=len(raw),
                mime=effective_mime,
            )
            repo.add(doc)
            session.commit()
            logger.info("doc_save 完成 id=%s name=%s size=%d", doc.id, doc.name, doc.size)
        return ok(
            data={"id": doc.id, "name": doc.name, "size": doc.size, "mime": doc.mime},
            message="保存成功",
        )
    except ValidationError as exc:
        logger.warning("doc_save 校验失败：%s", exc.message)
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("doc_save 未预期错误")
        return fail(message=f"保存失败：{exc}")


def _save_wecom(owner: str, name: str, raw: bytes, effective_mime: str) -> dict:
    """WECOM 分支：经 WeComDocClient 写入企微，storage_key 为企微 docid。"""
    client: WeComDocClient = build_wecom_client()
    ok_flag, doc_id, msg = client.write_doc(name.strip(), raw.decode("utf-8", errors="replace"))
    if not ok_flag:
        return fail(message=f"企微保存失败：{msg}")
    with db_engine.SessionLocal() as session:
        repo = DocumentRepository(session)
        doc = Document(
            id=uuid.uuid4().hex,
            owner_id=owner,
            name=name.strip(),
            provider="WECOM",
            storage_key=doc_id,
            size=len(raw),
            mime=effective_mime,
        )
        repo.add(doc)
        session.commit()
        logger.info("doc_save(WECOM) 完成 id=%s docid=%s", doc.id, doc_id)
    return ok(
        data={"id": doc.id, "name": doc.name, "size": doc.size, "mime": doc.mime, "provider": "WECOM"},
        message="企微保存成功",
    )


@mcp.tool(
    name="doc_read",
    description=(
        "读取文档原文内容（UTF-8 文本）；max_chars 控制返回长度，超长自动截断并标记 truncated。"
    ),
)
def doc_read(doc_id: str, max_chars: int = 100_000, provider: str = "") -> dict:
    """读取文档原文。provider=WECOM 时从企微侧读取（M9 骨架）。"""
    owner = _current_owner()
    try:
        if max_chars < 1:
            return fail(message="max_chars 必须大于 0")
        with db_engine.SessionLocal() as session:
            doc = DocumentRepository(session).get_by_owner(owner, doc_id)
            if doc is None:
                return fail(message="文档不存在")
            effective_provider = (provider or doc.provider or "LOCAL").strip().upper()
            if effective_provider not in _VALID_PROVIDERS:
                return fail(message=f"不支持的 provider：{effective_provider}")
            if effective_provider == "WECOM":
                return _read_wecom(doc, max_chars)
            raw = _storage().load(owner, doc.storage_key)
            provider_label = "LOCAL"
        text = raw.decode("utf-8", errors="replace")
        total = len(text)
        truncated = total > max_chars
        return ok(
            data={
                "id": doc.id,
                "name": doc.name,
                "mime": doc.mime,
                "content": text[:max_chars],
                "truncated": truncated,
                "total_chars": total,
                "provider": provider_label,
            },
            message="读取成功",
        )
    except NotFoundError as exc:
        return fail(message=exc.message)
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("doc_read 未预期错误")
        return fail(message=f"读取失败：{exc}")


def _read_wecom(doc: Document, max_chars: int) -> dict:
    """WECOM 分支：经 WeComDocClient 读取企微文档，保留截断逻辑。"""
    client: WeComDocClient = build_wecom_client()
    ok_flag, content, msg = client.read_doc(doc.storage_key)
    if not ok_flag:
        return fail(message=f"企微读取失败：{msg}")
    total = len(content)
    truncated = total > max_chars
    return ok(
        data={
            "id": doc.id,
            "name": doc.name,
            "mime": doc.mime,
            "content": content[:max_chars],
            "truncated": truncated,
            "total_chars": total,
            "provider": "WECOM",
        },
        message="企微读取成功",
    )


@mcp.tool(
    name="doc_search",
    description="按名称模糊 + MIME 过滤检索文档（当前用户可见范围），返回分页列表。",
)
def doc_search(name: str = "", mime: str = "", limit: int = 20, offset: int = 0) -> dict:
    """检索文档（name 模糊 / mime 精确）。"""
    owner = _current_owner()
    try:
        if not 1 <= limit <= _MAX_LIMIT:
            return fail(message=f"limit 需在 1~{_MAX_LIMIT} 之间")
        if offset < 0:
            return fail(message="offset 不能为负")
        with db_engine.SessionLocal() as session:
            docs = DocumentRepository(session).search_by_owner(
                owner, name=name, mime=mime, limit=limit, offset=offset
            )
        return ok(
            data={"items": [_doc_to_dict(d) for d in docs], "count": len(docs)},
            message=f"命中 {len(docs)} 条",
        )
    except Exception as exc:
        logger.exception("doc_search 未预期错误")
        return fail(message=f"检索失败：{exc}")


@mcp.tool(
    name="doc_list",
    description="分页列出当前用户全部文档（时间倒序）。",
)
def doc_list(limit: int = 20, offset: int = 0) -> dict:
    """列出文档。"""
    owner = _current_owner()
    try:
        if not 1 <= limit <= _MAX_LIMIT:
            return fail(message=f"limit 需在 1~{_MAX_LIMIT} 之间")
        if offset < 0:
            return fail(message="offset 不能为负")
        with db_engine.SessionLocal() as session:
            repo = DocumentRepository(session)
            docs = repo.search_by_owner(owner, limit=limit, offset=offset)
            total = len(repo.list_by_owner(owner))
        return ok(
            data={"items": [_doc_to_dict(d) for d in docs], "count": len(docs), "total": total},
            message=f"共 {total} 条",
        )
    except Exception as exc:
        logger.exception("doc_list 未预期错误")
        return fail(message=f"列出失败：{exc}")


@mcp.tool(
    name="doc_delete",
    description="删除文档（文件 + 元数据同时删除，跨用户越权访问被拒绝）。",
)
def doc_delete(doc_id: str) -> dict:
    """删除文档。"""
    owner = _current_owner()
    try:
        with db_engine.SessionLocal() as session:
            repo = DocumentRepository(session)
            doc = repo.get_by_owner(owner, doc_id)
            if doc is None:
                return fail(message="文档不存在")
            # 先删元数据（flush 未提交），再删文件，最后 commit 保持事务一致
            repo.delete_by_owner(owner, doc_id)
            _storage().delete(owner, doc.storage_key)
            session.commit()
            logger.info("doc_delete 完成 id=%s name=%s", doc.id, doc.name)
        return ok(data={"id": doc_id}, message="删除成功")
    except NotFoundError as exc:
        return fail(message=exc.message)
    except ValidationError as exc:
        return fail(message=exc.message)
    except Exception as exc:
        logger.exception("doc_delete 未预期错误")
        return fail(message=f"删除失败：{exc}")
