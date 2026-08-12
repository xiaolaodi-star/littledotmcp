"""M3-02 golden 测试：LocalDocStorage 防路径穿越、大小限制与 owner 目录隔离。"""

from __future__ import annotations

from pathlib import Path

import pytest

from littledotmcp.common.errors import NotFoundError, ValidationError
from littledotmcp.domains.doc.storage import DEFAULT_SIZE_LIMIT, LocalDocStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalDocStorage:
    return LocalDocStorage(tmp_path / "files")


def test_save_load_delete_roundtrip(storage: LocalDocStorage) -> None:
    key = storage.save("owner-a", b"hello world")
    assert key and "/" not in key and "\\" not in key
    assert storage.load("owner-a", key) == b"hello world"
    storage.delete("owner-a", key)
    with pytest.raises(NotFoundError):
        storage.load("owner-a", key)


def test_storage_key_generated_by_server(storage: LocalDocStorage) -> None:
    k1 = storage.save("owner-a", b"x")
    k2 = storage.save("owner-a", b"x")
    assert k1 != k2  # 每次由服务端生成新 key


@pytest.mark.parametrize("bad_key", ["../evil", "a/b", "a\\b", "", "..", ".", "a" * 200])
def test_load_rejects_unsafe_key(storage: LocalDocStorage, bad_key: str) -> None:
    with pytest.raises(ValidationError):
        storage.load("owner-a", bad_key)


@pytest.mark.parametrize("bad_owner", ["", ".", "..", "a/b", "a\\b"])
def test_save_rejects_unsafe_owner(storage: LocalDocStorage, bad_owner: str) -> None:
    with pytest.raises(ValidationError):
        storage.save(bad_owner, b"x")


def test_load_missing_file(storage: LocalDocStorage) -> None:
    with pytest.raises(NotFoundError):
        storage.load("owner-a", "0123456789abcdef")


def test_size_limit_rejected(storage: LocalDocStorage) -> None:
    with pytest.raises(ValidationError):
        storage.save("owner-a", b"x" * (DEFAULT_SIZE_LIMIT + 1))


def test_size_limit_custom(storage: LocalDocStorage) -> None:
    with pytest.raises(ValidationError):
        storage.save("owner-a", b"12345", size_limit=4)


def test_owner_directory_isolation(storage: LocalDocStorage) -> None:
    key_a = storage.save("owner-a", b"secret-a")
    # B 无法读取 A 的 key（同 key 在 B 目录下不存在）
    with pytest.raises(NotFoundError):
        storage.load("owner-b", key_a)
    # 文件落盘位置严格按 owner 分目录
    assert (storage.root / "owner-a" / key_a).is_file()
    assert not (storage.root / "owner-b" / key_a).exists()


def test_owner_dir_created_per_owner(storage: LocalDocStorage) -> None:
    storage.save("owner-a", b"x")
    storage.save("owner-b", b"y")
    assert (storage.root / "owner-a").is_dir()
    assert (storage.root / "owner-b").is_dir()
