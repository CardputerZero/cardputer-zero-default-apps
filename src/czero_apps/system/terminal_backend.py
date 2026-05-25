from __future__ import annotations

import os
from pathlib import Path

from czero_apps.system import command


TERMINALS = ["foot", "kgx", "lxterminal", "xterm", "x-terminal-emulator"]


def find_terminal() -> str | None:
    for name in TERMINALS:
        if command.available(name):
            return name
    return None


def launch(cwd: str | Path | None = None, diagnostic: bool = False):
    terminal = find_terminal()
    if terminal is None:
        return command.CommandResult(TERMINALS, 127, "", "no terminal backend installed")

    cwd_path = Path(cwd or Path.home())
    shell = os.environ.get("SHELL", "/bin/sh")
    if diagnostic:
        shell = "sh"
        args = [terminal, "-e", "sh", "-lc", "journalctl -b -n 80; exec sh"]
    elif terminal == "foot":
        args = [terminal, "--title=Zero Terminal", shell]
    elif terminal == "kgx":
        args = [terminal, "--working-directory", str(cwd_path)]
    elif terminal == "lxterminal":
        args = [terminal, "--working-directory", str(cwd_path)]
    elif terminal == "xterm":
        args = [terminal, "-T", "Zero Terminal", "-e", shell]
    else:
        args = [terminal]
    return command.spawn(args, cwd=cwd_path)
