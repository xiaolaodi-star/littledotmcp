"""SVN 客户端抽象与本地 mock 实现（M4-01）。

设计目标：在当前无 svn CLI 的本地环境下仍可测、可运行。
- SvnClient：外部 svn 操作的抽象协议（checkout/update/commit/log）。
- LocalFakeSvnClient：纯内存 + 临时目录模拟工作副本，不依赖真实 svn 命令；
  所有写操作会回调 ``on_op`` 写入 SvnOpLog，便于测试与审计。
- get_svn_client(repo)：工厂，默认返回 LocalFakeSvnClient；真实 CLI 后端留作
  可选扩展（环境变量 LITTLEDOT_SVN_BACKEND=cli 时启用，本次不实现）。

凭据处理：明文口令只在内存中短暂使用，落库前经 ``encrypt`` 转为 ``cred_enc``；
读取时 ``decrypt`` 还原。禁止明文入 DB。
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Callable, Protocol

# 轻量对称加密：用固定盐派生密钥，标准库实现（无外部依赖）。
# 注意：这是本地落库防明文泄露的最低限度保护，非强加密；生产环境应替换为
# 基于 KMS / 环境变量注入密钥的方案。
_SALT = b"littledot-svn-cred-salt"
_KEY = hashlib.pbkdf2_hmac("sha256", b"littledot-svn-static-key", _SALT, 100_000, dklen=32)


def _xor_crypt(data: bytes) -> bytes:
    out = bytearray(data)
    for i in range(len(out)):
        out[i] ^= _KEY[i % len(_KEY)]
    return bytes(out)


def encrypt(plain: str) -> str:
    """明文口令 -> 可入库的密文（base64(xor(key, utf8))）。"""
    if not plain:
        return ""
    return base64.b64encode(_xor_crypt(plain.encode("utf-8"))).decode("ascii")


def decrypt(cipher: str) -> str:
    """密文 -> 明文（仅内存中使用，绝不落库）。"""
    if not cipher:
        return ""
    return _xor_crypt(base64.b64decode(cipher)).decode("utf-8")


class SvnClient(Protocol):
    """SVN 外部操作的抽象。"""

    def checkout(self, local_path: Path, message: str = "") -> str:
        """检出到 local_path，返回 revision 字符串。"""
        ...

    def update(self, local_path: Path, message: str = "") -> str:
        """更新工作副本，返回新 revision 字符串。"""
        ...

    def commit(self, local_path: Path, message: str) -> str:
        """提交改动，返回新 revision 字符串。"""
        ...

    def log(self, local_path: Path) -> list[dict]:
        """返回提交历史（倒序）。"""
        ...


class LocalFakeSvnClient:
    """纯本地模拟客户端：用临时目录 + 内存历史记录模拟 svn 工作副本。"""

    def __init__(self, repo_id: str, on_op: Callable[[str, str, str], None] | None = None) -> None:
        self._repo_id = repo_id
        self._on_op = on_op
        # rev -> (message, op)
        self._history: list[tuple[str, str, str]] = []
        self._rev_counter = 0

    def _next_rev(self) -> str:
        self._rev_counter += 1
        return f"r{self._rev_counter}"

    def _record(self, op: str, message: str) -> str:
        rev = self._next_rev()
        self._history.append((rev, op, message))
        if self._on_op is not None:
            self._on_op(op, rev, message)
        return rev

    def checkout(self, local_path: Path, message: str = "") -> str:
        local_path.mkdir(parents=True, exist_ok=True)
        (local_path / ".svn_fake").write_text(f"repo={self._repo_id}\n", encoding="utf-8")
        return self._record("checkout", message or "checkout")

    def update(self, local_path: Path, message: str = "") -> str:
        local_path.mkdir(parents=True, exist_ok=True)
        return self._record("update", message or "update")

    def commit(self, local_path: Path, message: str) -> str:
        if not message.strip():
            raise ValueError("commit message 不能为空")
        local_path.mkdir(parents=True, exist_ok=True)
        return self._record("commit", message)

    def log(self, local_path: Path) -> list[dict]:
        return [
            {"rev": rev, "op": op, "message": msg}
            for rev, op, msg in reversed(self._history)
        ]


def get_svn_client(
    repo_id: str,
    *,
    on_op: Callable[[str, str, str], None] | None = None,
) -> SvnClient:
    """工厂：默认返回本地 mock 客户端。

    真实 CLI 后端（LITTLEDOT_SVN_BACKEND=cli）留作可选扩展，本次不实现。
    """
    backend = os.environ.get("LITTLEDOT_SVN_BACKEND", "fake").lower()
    if backend == "fake":
        return LocalFakeSvnClient(repo_id, on_op=on_op)
    raise NotImplementedError(f"未实现的 svn 后端：{backend}")
