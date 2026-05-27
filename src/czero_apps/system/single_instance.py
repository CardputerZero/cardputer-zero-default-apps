from __future__ import annotations

import fcntl
import os
import socket
import time
from pathlib import Path


class SingleInstance:
    def __init__(self, app_id: str) -> None:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        safe_name = app_id.replace("/", "_")
        self.path = Path(runtime) / "cardputer-zero" / f"{safe_name}.lock"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+", encoding="utf-8")
        self.acquired = False
        self.app_id = app_id

    def acquire(self) -> bool:
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            focus_running_app(self.app_id)
            return False
        self.acquired = True
        self.file.seek(0)
        self.file.truncate()
        self.file.write(f"{os.getpid()}\n{time.time():.3f}\n")
        self.file.flush()
        return True

    def close(self) -> None:
        if self.acquired:
            try:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self.file.close()


def focus_running_app(app_id: str) -> None:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return
    sock_path = Path(runtime) / "cardputer-zero" / "window-agent.sock"
    if not sock_path.exists():
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(str(sock_path))
            sock.sendall(b"list\n")
            data = b""
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"snapshot-end\n" in data:
                    break
            task_id = task_for_app(data.decode("utf-8", "replace"), app_id)
            if task_id:
                sock.sendall(f"activate\t{task_id}\n".encode("utf-8"))
    except OSError:
        return


def task_for_app(snapshot: str, app_id: str) -> str:
    expected = app_id.lower()
    for line in snapshot.splitlines():
        fields = line.split("\t")
        if len(fields) >= 5 and fields[0] == "task" and fields[2].lower() == expected:
            return fields[1]
    return ""


def run_single_instance(app_id: str, run_app) -> int:
    instance = SingleInstance(app_id)
    if not instance.acquire():
        return 0
    try:
        return int(run_app() or 0)
    finally:
        instance.close()


__all__ = ["run_single_instance"]
