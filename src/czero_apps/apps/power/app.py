from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cairo

from czero_apps.ui.gtk import Gdk, GLib, Gtk
from czero_apps.ui.theme import load_css


WIDTH = 320
HEIGHT = 170
MAIN_H = 150
BOTTOM_H = 20

PANEL_X = 56
PANEL_Y = 8
PANEL_W = 208
PANEL_H = 134

ZERO_PAPER = (0xE9 / 255, 0xE4 / 255, 0xD5 / 255)
PANEL_CREAM = (0xF4 / 255, 0xF0 / 255, 0xE6 / 255)
ICON_WELL = (0xF8 / 255, 0xF4 / 255, 0xEA / 255)
INK_BLACK = (0x17 / 255, 0x17 / 255, 0x17 / 255)
LINE_BLACK = (0x2A / 255, 0x2A / 255, 0x2A / 255)
MUTED_TEXT = (0x6E / 255, 0x6A / 255, 0x61 / 255)
ACCENT_ORANGE = (0xE6 / 255, 0x6A / 255, 0x2C / 255)
OK_GREEN = (0x3A / 255, 0x7D / 255, 0x44 / 255)
WARN_RED = (0xB9 / 255, 0x4A / 255, 0x2C / 255)
HARD_SHADOW = (0xBD / 255, 0xB5 / 255, 0xA4 / 255)
SELECT_FILL = (0xFB / 255, 0xEE / 255, 0xDD / 255)
TITLE_FILL = (0xF0 / 255, 0xD2 / 255, 0xBD / 255)

Mode = Literal["main", "confirm", "executing", "error"]


DEFAULT_CONFIG = {
    "default_action": "display_off",
    "confirm_reboot": True,
    "confirm_shutdown": True,
    "confirm_logout": True,
    "display_off_backend": "auto",
    "logout_backend": "auto",
    "show_power_status": True,
}


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    code: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.error and not self.timed_out

    @property
    def message(self) -> str:
        return (self.error or self.stderr.strip() or self.stdout.strip() or "Command failed").strip()


class CommandRunner:
    def which(self, command: str) -> str | None:
        return shutil.which(command)

    def available(self, command: str) -> bool:
        return self.which(command) is not None

    def run(self, args: list[str], timeout: int = 8) -> CommandResult:
        try:
            completed = subprocess.run(
                args,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return CommandResult(args=args, code=127, error=f"{args[0]} not installed.")
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                args=args,
                code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                error=f"{args[0]} timed out.",
                timed_out=True,
            )
        except OSError as exc:
            return CommandResult(args=args, code=1, error=str(exc))
        return CommandResult(args=args, code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


@dataclass(frozen=True)
class PowerStatus:
    text: str
    ok: bool = False
    warn: bool = False


class PowerStatusBackend:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def status(self) -> PowerStatus:
        if self.runner.available("upower"):
            status = self._from_upower()
            if status:
                return status
        status = self._from_sysfs()
        if status:
            return status
        return PowerStatus("Power | Unknown")

    def _from_upower(self) -> PowerStatus | None:
        devices = self.runner.run(["upower", "-e"], timeout=2)
        if not devices.ok:
            return None
        lines = [line.strip() for line in devices.stdout.splitlines() if line.strip()]
        battery = next((line for line in lines if "battery" in line.lower()), None)
        if battery:
            info = self.runner.run(["upower", "-i", battery], timeout=2)
            if not info.ok:
                return None
            percent = self._match_value(info.stdout, r"percentage:\s*([0-9]+%)")
            state = self._match_value(info.stdout, r"state:\s*(\S+)")
            if percent:
                return self._battery_status(percent, state or "Battery")
        line_power = next((line for line in lines if "line_power" in line.lower()), None)
        if line_power:
            return PowerStatus("USB-C | Powered", ok=True)
        return None

    def _from_sysfs(self) -> PowerStatus | None:
        root = Path("/sys/class/power_supply")
        if not root.exists():
            return None
        supplies = list(root.iterdir())
        for supply in supplies:
            if self._read(supply / "type").lower() == "battery":
                capacity = self._read(supply / "capacity")
                state = self._read(supply / "status") or "Battery"
                if capacity:
                    return self._battery_status(f"{capacity}%", state)
        for supply in supplies:
            supply_type = self._read(supply / "type").lower()
            online = self._read(supply / "online")
            if supply_type in {"usb", "usb_c", "mains", "ac"} and online in {"1", ""}:
                return PowerStatus("USB-C | Powered", ok=True)
        return None

    def _battery_status(self, percent: str, state: str) -> PowerStatus:
        try:
            value = int(percent.rstrip("%"))
        except ValueError:
            value = 100
        state_label = state.replace("-", " ").title()
        if value <= 15 and state.lower() not in {"charging", "fully-charged"}:
            return PowerStatus(f"{percent} | {state_label}", warn=True)
        return PowerStatus(f"{percent} | {state_label}", ok=state.lower() in {"charging", "fully-charged"})

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def _match_value(text_value: str, pattern: str) -> str | None:
        match = re.search(pattern, text_value, re.IGNORECASE)
        return match.group(1).strip() if match else None


class PowerBackend:
    def __init__(self, runner: CommandRunner, config: dict) -> None:
        self.runner = runner
        self.config = config

    def display_off(self) -> CommandResult:
        backend = str(self.config.get("display_off_backend", "auto"))
        if backend in {"auto", "wlopm"} and self.runner.available("wlopm"):
            return self.runner.run(["wlopm", "--off", "*"], timeout=10)
        if backend in {"auto", "xset"} and self.runner.available("xset"):
            return self.runner.run(["xset", "dpms", "force", "off"], timeout=10)
        if backend in {"auto", "loginctl"} and self.runner.available("loginctl"):
            session = os.environ.get("XDG_SESSION_ID")
            if session:
                return self.runner.run(["loginctl", "lock-session", session], timeout=10)
            return self.runner.run(["loginctl", "lock-session"], timeout=10)
        return CommandResult(args=["display-off"], code=127, error="Display off is not available.")

    def suspend(self) -> CommandResult:
        return self.runner.run(["systemctl", "suspend"], timeout=20)

    def reboot(self) -> CommandResult:
        return self.runner.run(["systemctl", "reboot"], timeout=20)

    def shutdown(self) -> CommandResult:
        return self.runner.run(["systemctl", "poweroff"], timeout=20)

    def logout(self) -> CommandResult:
        backend = str(self.config.get("logout_backend", "auto"))
        if backend in {"auto", "helper"} and self.runner.available("cardputer-zero-session-logout"):
            return self.runner.run(["cardputer-zero-session-logout"], timeout=10)
        if backend in {"auto", "loginctl"} and self.runner.available("loginctl"):
            session = self.cardputer_zero_session_id() or os.environ.get("XDG_SESSION_ID")
            if session:
                return self.runner.run(["loginctl", "terminate-session", str(session)], timeout=10)
            user = os.environ.get("USER") or os.environ.get("LOGNAME")
            if user:
                return self.runner.run(["loginctl", "terminate-user", user], timeout=10)
        return CommandResult(args=["logout"], code=127, error="Logout is not available.")

    def cardputer_zero_session_id(self) -> str | None:
        sessions = self.runner.run(["loginctl", "list-sessions", "--no-legend"], timeout=3)
        if not sessions.ok:
            return None
        user = os.environ.get("USER") or os.environ.get("LOGNAME")
        candidates: list[str] = []
        for line_value in sessions.stdout.splitlines():
            parts = line_value.split()
            if len(parts) < 3:
                continue
            session_id = parts[0]
            if user and parts[2] != user:
                continue
            details = self.session_properties(session_id)
            if not details:
                continue
            if details.get("Remote") == "yes":
                continue
            if details.get("Service") == "cardputer-zero-session":
                return session_id
            if details.get("Desktop") == "CardputerZero" and details.get("Type") == "wayland":
                candidates.append(session_id)
        return candidates[0] if candidates else None

    def session_properties(self, session_id: str | int) -> dict[str, str]:
        result = self.runner.run(
            [
                "loginctl",
                "show-session",
                str(session_id),
                "-p",
                "Service",
                "-p",
                "Desktop",
                "-p",
                "Type",
                "-p",
                "Remote",
                "--no-pager",
            ],
            timeout=3,
        )
        if not result.ok:
            return {}
        values: dict[str, str] = {}
        for line_value in result.stdout.splitlines():
            key, sep, value = line_value.partition("=")
            if sep:
                values[key] = value
        return values


@dataclass(frozen=True)
class PowerAction:
    id: str
    label: str
    icon: str
    dangerous: bool = False
    requires_confirm: bool = False
    enabled: bool = True
    error_if_disabled: str = ""


@dataclass
class PowerAppState:
    selected_action_index: int
    mode: Mode
    confirm_action: PowerAction | None
    selected_confirm_button: int
    power_status: PowerStatus
    error_message: str
    error_until: float
    executing_message: str


def config_path() -> Path:
    return Path.home() / ".config" / "cardputer-zero" / "default-apps" / "power.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        save_config(dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        config = dict(DEFAULT_CONFIG)
        if isinstance(loaded, dict):
            config.update(loaded)
        return config
    except Exception:
        backup = path.with_suffix(".json.bak")
        try:
            path.replace(backup)
        except OSError:
            pass
        save_config(dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def set_color(ctx: cairo.Context, color: tuple[float, float, float]) -> None:
    ctx.set_source_rgb(*color)


def configure_crisp(ctx: cairo.Context) -> None:
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_NONE)
    ctx.set_font_options(options)


def fill_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float]) -> None:
    ctx.new_path()
    set_color(ctx, color)
    ctx.rectangle(x, y, w, h)
    ctx.fill()
    ctx.new_path()


def stroke_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float] = LINE_BLACK) -> None:
    ctx.new_path()
    set_color(ctx, color)
    ctx.set_line_width(1)
    ctx.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
    ctx.stroke()
    ctx.new_path()


def line(ctx: cairo.Context, x1: int, y1: int, x2: int, y2: int, color: tuple[float, float, float] = LINE_BLACK) -> None:
    ctx.new_path()
    set_color(ctx, color)
    ctx.set_line_width(1)
    ctx.move_to(x1 + 0.5, y1 + 0.5)
    ctx.line_to(x2 + 0.5, y2 + 0.5)
    ctx.stroke()
    ctx.new_path()


def panel(ctx: cairo.Context, x: int, y: int, w: int, h: int) -> None:
    fill_rect(ctx, x + 2, y + 2, w, h, HARD_SHADOW)
    fill_rect(ctx, x, y, w, h, PANEL_CREAM)
    stroke_rect(ctx, x, y, w, h)


def text(
    ctx: cairo.Context,
    value: str,
    x: int,
    y: int,
    color: tuple[float, float, float] = INK_BLACK,
    size: int = 9,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> None:
    set_color(ctx, color)
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    ctx.move_to(x, y)
    ctx.show_text(value)


def text_width(ctx: cairo.Context, value: str, size: int = 9, weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL) -> int:
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    return int(ctx.text_extents(value).width)


def text_center(
    ctx: cairo.Context,
    value: str,
    center_x: int,
    y: int,
    color: tuple[float, float, float] = INK_BLACK,
    size: int = 9,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> None:
    text(ctx, value, center_x - text_width(ctx, value, size, weight) // 2, y, color, size, weight)


def fit_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 2:
        return value[:limit]
    return value[: limit - 2] + ".."


def keycap(ctx: cairo.Context, x: int, y: int, label: str, w: int) -> None:
    top_h = 12
    fill_rect(ctx, x + 1, y + top_h + 1, w, 3, HARD_SHADOW)
    fill_rect(ctx, x, y, w, top_h + 1, ICON_WELL)
    set_color(ctx, LINE_BLACK)
    ctx.set_line_width(1)
    ctx.move_to(x + 2.5, y + 0.5)
    ctx.line_to(x + w - 2.5, y + 0.5)
    ctx.line_to(x + w - 0.5, y + 2.5)
    ctx.line_to(x + w - 0.5, y + top_h + 0.5)
    ctx.line_to(x + w - 2.5, y + top_h + 2.5)
    ctx.line_to(x + 2.5, y + top_h + 2.5)
    ctx.line_to(x + 0.5, y + top_h + 0.5)
    ctx.line_to(x + 0.5, y + 2.5)
    ctx.close_path()
    ctx.stroke()
    line(ctx, x + 2, y + top_h, x + w - 3, y + top_h)
    line(ctx, x + 3, y + top_h + 2, x + w - 5, y + top_h + 2)
    text_center(ctx, label, x + w // 2, y + 10, INK_BLACK, 8, cairo.FONT_WEIGHT_BOLD)


ICON_NAMES = ("display", "moon", "reboot", "power", "logout", "battery", "warn")
ICON_SIZE = 16
ICON_SHEET: cairo.ImageSurface | None = None


def icon_sheet() -> cairo.ImageSurface:
    global ICON_SHEET
    if ICON_SHEET is None:
        ICON_SHEET = cairo.ImageSurface.create_from_png(str(Path(__file__).with_name("power-icons.png")))
    return ICON_SHEET


def icon_color_row(color: tuple[float, float, float]) -> int:
    if color == ACCENT_ORANGE:
        return 1
    if color == WARN_RED:
        return 2
    return 0


def draw_icon(ctx: cairo.Context, icon: str, x: int, y: int, color: tuple[float, float, float] = INK_BLACK) -> None:
    try:
        col = ICON_NAMES.index(icon)
    except ValueError:
        col = ICON_NAMES.index("power")
    row = icon_color_row(color)
    ctx.save()
    ctx.rectangle(x, y, ICON_SIZE, ICON_SIZE)
    ctx.clip()
    ctx.set_source_surface(icon_sheet(), x - col * ICON_SIZE, y - row * ICON_SIZE)
    ctx.paint()
    ctx.restore()


class PowerStatusStrip:
    def draw(self, ctx: cairo.Context, status: PowerStatus, x: int, y: int, w: int, h: int) -> None:
        fill_rect(ctx, x, y, w, h, ICON_WELL)
        stroke_rect(ctx, x, y, w, h)
        draw_icon(ctx, "battery", x + 8, y + 2)
        color = WARN_RED if status.warn else OK_GREEN if status.ok else MUTED_TEXT
        text_center(ctx, fit_text(status.text, 21), x + w // 2 + 9, y + 12, color, 9, cairo.FONT_WEIGHT_BOLD if status.ok or status.warn else cairo.FONT_WEIGHT_NORMAL)


class PowerActionButton:
    def __init__(self, action: PowerAction) -> None:
        self.action = action

    def draw(self, ctx: cairo.Context, x: int, y: int, w: int, h: int, selected: bool) -> None:
        fill_rect(ctx, x + 2, y + 2, w, h, HARD_SHADOW)
        fill_rect(ctx, x, y, w, h, SELECT_FILL if selected else ICON_WELL)
        stroke_rect(ctx, x, y, w, h, ACCENT_ORANGE if selected else LINE_BLACK)
        color = ACCENT_ORANGE if selected else INK_BLACK
        draw_icon(ctx, self.action.icon, x + 7, y + max(2, h // 2 - 9), color)
        text(
            ctx,
            fit_text(self.action.label, 11),
            x + 29,
            y + h // 2 + 4,
            color,
            8,
            cairo.FONT_WEIGHT_BOLD if selected else cairo.FONT_WEIGHT_NORMAL,
        )


class ErrorBanner:
    def draw(self, ctx: cairo.Context, message: str) -> None:
        x = PANEL_X + 9
        y = PANEL_Y + PANEL_H - 24
        w = PANEL_W - 18
        fill_rect(ctx, x, y, w, 18, SELECT_FILL)
        stroke_rect(ctx, x, y, w, 18, WARN_RED)
        draw_icon(ctx, "warn", x + 5, y + 1, WARN_RED)
        text(ctx, fit_text(message, 27), x + 25, y + 12, WARN_RED, 8, cairo.FONT_WEIGHT_BOLD)


class ConfirmPage:
    MESSAGES = {
        "reboot": ("Reboot?", "This will restart the device.", "Reboot"),
        "shutdown": ("Shutdown?", "This will power off the device.", "Shutdown"),
        "logout": ("Logout?", "This will close the current session.", "Logout"),
    }

    def draw(self, ctx: cairo.Context, action: PowerAction, selected_button: int) -> None:
        title, body, confirm_label = self.MESSAGES.get(action.id, ("Confirm?", "Run selected action.", action.label))
        text_center(ctx, title, PANEL_X + PANEL_W // 2, PANEL_Y + 32, INK_BLACK, 14, cairo.FONT_WEIGHT_BOLD)
        text_center(ctx, fit_text(body, 32), PANEL_X + PANEL_W // 2, PANEL_Y + 56, MUTED_TEXT, 9)
        draw_icon(ctx, action.icon, PANEL_X + PANEL_W // 2 - 9, PANEL_Y + 66, WARN_RED if action.dangerous else INK_BLACK)
        self._button(ctx, PANEL_X + 32, PANEL_Y + 98, 62, 22, "Cancel", selected_button == 0, False)
        self._button(ctx, PANEL_X + 113, PANEL_Y + 98, 64, 22, confirm_label, selected_button == 1, action.dangerous)

    def _button(self, ctx: cairo.Context, x: int, y: int, w: int, h: int, label: str, selected: bool, danger: bool) -> None:
        fill_rect(ctx, x + 2, y + 2, w, h, HARD_SHADOW)
        fill_rect(ctx, x, y, w, h, SELECT_FILL if selected else ICON_WELL)
        border = ACCENT_ORANGE if selected else WARN_RED if danger else LINE_BLACK
        stroke_rect(ctx, x, y, w, h, border)
        label_color = WARN_RED if danger else INK_BLACK
        if selected:
            label_color = ACCENT_ORANGE
        text_center(ctx, fit_text(label, 9), x + w // 2, y + 14, label_color, 9, cairo.FONT_WEIGHT_BOLD if selected or danger else cairo.FONT_WEIGHT_NORMAL)


class PowerPanel:
    def __init__(self, actions: tuple[PowerAction, ...]) -> None:
        self.actions = actions
        self.status_strip = PowerStatusStrip()
        self.confirm_page = ConfirmPage()
        self.error_banner = ErrorBanner()

    def draw(self, ctx: cairo.Context, state: PowerAppState) -> None:
        panel(ctx, PANEL_X, PANEL_Y, PANEL_W, PANEL_H)
        fill_rect(ctx, PANEL_X + 1, PANEL_Y + 1, PANEL_W - 2, 18, TITLE_FILL)
        text_center(ctx, "Power", PANEL_X + PANEL_W // 2, PANEL_Y + 14, INK_BLACK, 12, cairo.FONT_WEIGHT_BOLD)
        line(ctx, PANEL_X, PANEL_Y + 19, PANEL_X + PANEL_W - 1, PANEL_Y + 19)
        if state.mode == "confirm" and state.confirm_action:
            self.confirm_page.draw(ctx, state.confirm_action, state.selected_confirm_button)
        elif state.mode == "executing":
            self._draw_executing(ctx, state.executing_message)
        else:
            self._draw_main(ctx, state)
        if state.error_message and time.monotonic() < state.error_until:
            self.error_banner.draw(ctx, state.error_message)

    def _draw_main(self, ctx: cairo.Context, state: PowerAppState) -> None:
        self.status_strip.draw(ctx, state.power_status, PANEL_X + 14, PANEL_Y + 25, PANEL_W - 28, 18)
        positions = (
            (PANEL_X + 17, PANEL_Y + 52, 82, 18),
            (PANEL_X + 109, PANEL_Y + 52, 82, 18),
            (PANEL_X + 17, PANEL_Y + 78, 82, 18),
            (PANEL_X + 109, PANEL_Y + 78, 82, 18),
        )
        for index, rect in enumerate(positions):
            PowerActionButton(self.actions[index]).draw(ctx, *rect, selected=index == state.selected_action_index)
        PowerActionButton(self.actions[4]).draw(
            ctx,
            PANEL_X + 64,
            PANEL_Y + 104,
            80,
            18,
            selected=state.selected_action_index == 4,
        )

    def _draw_executing(self, ctx: cairo.Context, message: str) -> None:
        fill_rect(ctx, PANEL_X + 21, PANEL_Y + 43, PANEL_W - 42, 52, ICON_WELL)
        stroke_rect(ctx, PANEL_X + 21, PANEL_Y + 43, PANEL_W - 42, 52)
        text_center(ctx, message, PANEL_X + PANEL_W // 2, PANEL_Y + 67, ACCENT_ORANGE, 11, cairo.FONT_WEIGHT_BOLD)
        text_center(ctx, "System will handle authorization.", PANEL_X + PANEL_W // 2, PANEL_Y + 84, MUTED_TEXT, 8)


class BottomBar:
    def draw(self, ctx: cairo.Context) -> None:
        y = MAIN_H
        fill_rect(ctx, 0, y, WIDTH, BOTTOM_H, ZERO_PAPER)
        line(ctx, 0, y, WIDTH, y)
        keycap(ctx, 5, y + 3, "ARROWS", 52)
        text(ctx, "Select", 63, y + 13, INK_BLACK, 8)
        keycap(ctx, 121, y + 3, "ENTER", 43)
        text(ctx, "Confirm", 170, y + 13, INK_BLACK, 8)
        keycap(ctx, 252, y + 3, "ESC", 34)
        text(ctx, "Back", 291, y + 13, INK_BLACK, 8)


class PowerCanvas(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.runner = CommandRunner()
        self.backend = PowerBackend(self.runner, self.config)
        self.status_backend = PowerStatusBackend(self.runner)
        self.actions = self._actions()
        default_index = self._default_index()
        self.state = PowerAppState(
            selected_action_index=default_index,
            mode="main",
            confirm_action=None,
            selected_confirm_button=0,
            power_status=self.status_backend.status(),
            error_message="",
            error_until=0.0,
            executing_message="",
        )
        self.panel = PowerPanel(self.actions)
        self.bottom_bar = BottomBar()
        self.set_content_width(WIDTH)
        self.set_content_height(HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_focusable(True)
        self.set_draw_func(self._draw)
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        GLib.timeout_add_seconds(3, self.refresh_status)

    def _actions(self) -> tuple[PowerAction, ...]:
        return (
            PowerAction("display_off", "Display Off", "display"),
            PowerAction("suspend", "Suspend", "moon"),
            PowerAction("reboot", "Reboot", "reboot", dangerous=True, requires_confirm=bool(self.config.get("confirm_reboot", True))),
            PowerAction("shutdown", "Shutdown", "power", dangerous=True, requires_confirm=bool(self.config.get("confirm_shutdown", True))),
            PowerAction("logout", "Logout", "logout", requires_confirm=bool(self.config.get("confirm_logout", True))),
        )

    def _default_index(self) -> int:
        default_id = str(self.config.get("default_action", "display_off"))
        for index, action in enumerate(self.actions):
            if action.id == default_id:
                return index
        return 0

    def refresh_status(self) -> bool:
        if self.config.get("show_power_status", True):
            self.state.power_status = self.status_backend.status()
            self.queue_draw()
        return True

    def _draw(self, _area: Gtk.DrawingArea, ctx: cairo.Context, _width: int, _height: int) -> None:
        configure_crisp(ctx)
        fill_rect(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
        self.panel.draw(ctx, self.state)
        self.bottom_bar.draw(ctx)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            self.close_window()
            return True
        if self.state.mode == "executing":
            return True
        handled = self._handle_confirm_key(keyval) if self.state.mode == "confirm" else self._handle_main_key(keyval)
        if handled:
            self.queue_draw()
        return handled

    def _handle_main_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_BackSpace):
            self.close_window()
            return True
        if keyval == Gdk.KEY_Left:
            self.move_horizontal(-1)
        elif keyval == Gdk.KEY_Right:
            self.move_horizontal(1)
        elif keyval == Gdk.KEY_Up:
            self.move_vertical(-1)
        elif keyval == Gdk.KEY_Down:
            self.move_vertical(1)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate_selected_action()
        else:
            return False
        return True

    def _handle_confirm_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_BackSpace):
            self.state.mode = "main"
            self.state.confirm_action = None
            self.state.selected_confirm_button = 0
        elif keyval == Gdk.KEY_Left:
            self.state.selected_confirm_button = 0
        elif keyval == Gdk.KEY_Right:
            self.state.selected_confirm_button = 1
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.state.selected_confirm_button == 0:
                self.state.mode = "main"
                self.state.confirm_action = None
            elif self.state.confirm_action:
                self.run_action(self.state.confirm_action)
        else:
            return False
        return True

    def move_horizontal(self, delta: int) -> None:
        index = self.state.selected_action_index
        if index >= 4:
            return
        row = index // 2
        col = index % 2
        col = max(0, min(1, col + delta))
        self.state.selected_action_index = row * 2 + col

    def move_vertical(self, delta: int) -> None:
        index = self.state.selected_action_index
        if delta > 0:
            if index in (0, 1):
                self.state.selected_action_index = index + 2
            elif index in (2, 3):
                self.state.selected_action_index = 4
        else:
            if index == 4:
                self.state.selected_action_index = 2
            elif index in (2, 3):
                self.state.selected_action_index = index - 2

    def activate_selected_action(self) -> None:
        action = self.actions[self.state.selected_action_index]
        if not action.enabled:
            self.show_error(action.error_if_disabled or f"{action.label} unavailable.")
            return
        if action.requires_confirm:
            self.state.mode = "confirm"
            self.state.confirm_action = action
            self.state.selected_confirm_button = 0
            return
        self.run_action(action)

    def run_action(self, action: PowerAction) -> None:
        self.state.mode = "executing"
        self.state.executing_message = {
            "display_off": "Turning display off...",
            "suspend": "Suspending...",
            "reboot": "Rebooting...",
            "shutdown": "Shutting down...",
            "logout": "Logging out...",
        }.get(action.id, f"{action.label}...")
        self.queue_draw()
        threading.Thread(target=self._run_backend_action, args=(action,), daemon=True).start()

    def _run_backend_action(self, action: PowerAction) -> None:
        result = {
            "display_off": self.backend.display_off,
            "suspend": self.backend.suspend,
            "reboot": self.backend.reboot,
            "shutdown": self.backend.shutdown,
            "logout": self.backend.logout,
        }[action.id]()
        GLib.idle_add(self._finish_backend_action, action, result)

    def _finish_backend_action(self, action: PowerAction, result: CommandResult) -> bool:
        if result.ok:
            if action.id in {"display_off", "suspend"}:
                self.state.mode = "main"
                self.state.confirm_action = None
                self.state.executing_message = ""
        else:
            self.state.mode = "main"
            self.state.confirm_action = None
            self.show_error(self.friendly_error(result))
        self.queue_draw()
        return False

    def friendly_error(self, result: CommandResult) -> str:
        message = result.message
        lower = message.lower()
        if result.code == 127:
            return message
        if "permission" in lower or "access denied" in lower or "not authorized" in lower:
            return "Permission denied. Authorization may be required."
        if result.args:
            return f"{Path(result.args[0]).name} failed."
        return fit_text(message, 32)

    def show_error(self, message: str) -> None:
        self.state.error_message = message
        self.state.error_until = time.monotonic() + 3.0
        self.queue_draw()

    def close_window(self) -> None:
        root = self.get_root()
        if isinstance(root, Gtk.Window):
            root.close()


class PowerApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.cardputerzero.defaultapps.power")

    def do_activate(self) -> None:
        load_css()
        window = Gtk.ApplicationWindow(application=self, title="Power")
        window.set_default_size(WIDTH, HEIGHT)
        window.set_size_request(WIDTH, HEIGHT)
        window.set_resizable(False)
        window.set_decorated(False)
        canvas = PowerCanvas()
        window.set_child(canvas)
        window.present()
        GLib.idle_add(canvas.grab_focus)


def run(argv: list[str] | None = None) -> int:
    app = PowerApp()
    return app.run(argv or [])
