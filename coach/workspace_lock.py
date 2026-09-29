"""Bounded OS advisory lock; released by the OS on crash. No stale lock guessing."""
import contextlib
import os
import time


@contextlib.contextmanager
def locked(workspace, timeout=2.0):
    os.makedirs(workspace, exist_ok=True)
    path = os.path.join(workspace, ".crushexam.lock")
    handle = open(path, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("该工作区正被另一个命令使用；本次未修改状态。请待正在运行的命令结束后重试。")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
