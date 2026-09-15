"""共享工具 — 跨进程文件锁与原子写

收敛 settings/config/db_store/chain/error_log/perf_log 各自复制的同构实现。
锁路径语义由调用方决定并保持不变（如 seek.json.lock / {session_id}.lock），
保证新旧版本 CLI 进程混跑时仍然互斥。
"""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(lock_path: Path):
    """跨进程排他锁（fcntl.flock）；fcntl 不可用的平台降级为无锁。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        try:
            import fcntl
        except ImportError:
            yield
            return
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: Path, data, *, indent: int = 2,
                      default=None, chmod_0600: bool = False) -> None:
    """原子写 JSON：mkstemp → dump → fsync →（可选 chmod）→ os.replace。

    异常时清理临时文件并上抛，目标文件保持写入前的完整状态。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp",
                                     dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, default=default)
            f.flush()
            os.fsync(f.fileno())
        if chmod_0600:
            import stat
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str,
                      chmod_0600: bool = False) -> None:
    """原子写纯文本（用于空文件替换等非 JSON 场景）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp",
                                     dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if chmod_0600:
            import stat
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise
