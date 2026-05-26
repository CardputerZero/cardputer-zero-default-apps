from __future__ import annotations

import sys


APP_MODULES = {
    "settings": "czero_apps.apps.settings.app",
    "terminal": "czero_apps.apps.terminal.app",
    "files": "czero_apps.apps.files.app",
    "power": "czero_apps.apps.power.app",
    "monitor": "czero_apps.apps.monitor.app",
    "store": "czero_apps.apps.store.app",
    "robot": "czero_apps.apps.robot.app",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in APP_MODULES:
        names = ", ".join(sorted(APP_MODULES))
        print(f"usage: czero-app <{names}> [args...]", file=sys.stderr)
        return 2

    app_name = argv.pop(0)
    module_name = APP_MODULES[app_name]
    module = __import__(module_name, fromlist=["run"])
    return int(module.run(argv) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
