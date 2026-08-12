"""M3-02 DocStorage 抽象与本地实现（防路径穿越 + owner 分目录）。

安全要点：
- storage_key 由服务端生成（UUID），仅允许安全字符，拒绝用户路径输入；
- load/delete 对合成路径 resolve() 后断言仍位于 owner 子目录内（防 `..` 穿越）；
- save 校验内容大小上限。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol

from ...common.errors import NotFoundError, ValidationError
from ...common.logging import get_logger

logger = get_logger(__name__)

# storage_key 仅允许安全字符（服务端生成 UUID，杜绝用户传入路径）
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# 单文件默认大小上限：50MB
DEFAULT_SIZE_LIMIT = 50 * 1024 * 1024

# owner_id 禁用的路径分隔符与保留值，防止跨目录
_FORBIDDEN_OWNER = {"", ".", ".."}


class DocStorage(Protocol):
    """文档存储抽象：save/load/delete。实现可为本地文件或企微（M3-03）。"""

    def save(self, owner_id: str, content: bytes, *, size_limit: int = DEFAULT_SIZE_LIMIT) -> str:
        """保存内容，返回服务端生成的 storage_key。"""

    def load(self, owner_id: str, storage_key: str) -> bytes:
        """按 owner 与 key 读取原文；不存在抛 NotFoundError。"""

    def delete(self, owner_id: str, storage_key: str) -> None:
        """删除文件（幂等：不存在不报错）。"""


class LocalDocStorage:
    """本地文件存储：storage_root / owner_id / storage_key。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, owner_id: str, content: bytes, *, size_limit: int = DEFAULT_SIZE_LIMIT) -> str:
        if not isinstance(content, bytes):
            raise ValidationError("内容必须是字节串")
        if len(content) > size_limit:
            raise ValidationError(f"文件超过大小限制 {size_limit} 字节（当前 {len(content)}）")
        owner_dir = self._owner_dir(owner_id)
        owner_dir.mkdir(parents=True, exist_ok=True)
        storage_key = uuid.uuid4().hex
        (owner_dir / storage_key).write_bytes(content)
        logger.info("doc 已保存 owner=%s key=%s size=%d", owner_id, storage_key, len(content))
        return storage_key

    def load(self, owner_id: str, storage_key: str) -> bytes:
        return self._resolve(owner_id, storage_key).read_bytes()

    def delete(self, owner_id: str, storage_key: str) -> None:
        path = self._resolve(owner_id, storage_key)
        path.unlink(missing_ok=True)
        logger.info("doc 已删除 owner=%s key=%s", owner_id, storage_key)

    def _owner_dir(self, owner_id: str) -> Path:
        if owner_id in _FORBIDDEN_OWNER or "/" in owner_id or "\\" in owner_id:
            raise ValidationError("非法 owner_id")
        return self.root / owner_id

    def _resolve(self, owner_id: str, storage_key: str) -> Path:
        if not _SAFE_KEY.match(storage_key):
            raise ValidationError("非法的 storage_key")
        owner_dir = self._owner_dir(owner_id).resolve()
        path = (self.root / owner_id / storage_key).resolve()
        if not path.is_relative_to(owner_dir):
            raise ValidationError("路径越界，拒绝访问")
        if not path.is_file():
            raise NotFoundError(f"文档文件不存在：{storage_key}")
        return path
