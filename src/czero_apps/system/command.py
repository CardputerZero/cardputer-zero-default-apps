from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def text(self) -> str:
        return self.stdout.strip() or self.stderr.strip()


def which(command: str) -> str | None:
    return shutil.which(command)


def available(command: str) -> bool:
    return which(command) is not None


def run(args: list[str], timeout: int = 10, cwd: str | Path | None = None) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CommandResult(args, completed.returncode, completed.stdout, completed.stderr)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(args, 124, exc.stdout or "", exc.stderr or "timeout", True)
    except FileNotFoundError as exc:
        return CommandResult(args, 127, "", str(exc))


def spawn(args: list[str], cwd: str | Path | None = None) -> CommandResult:
    try:
        subprocess.Popen(args, cwd=str(cwd) if cwd else None)
        return CommandResult(args, 0, "", "")
    except FileNotFoundError as exc:
        return CommandResult(args, 127, "", str(exc))
    except OSError as exc:
        return CommandResult(args, 1, "", str(exc))
