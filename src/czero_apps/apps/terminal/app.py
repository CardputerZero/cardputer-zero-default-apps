from __future__ import annotations

import codecs
import fcntl
import json
import os
import pty
import re
import signal
import struct
import subprocess
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

if os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("GDK_BACKEND", "wayland")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from czero_apps.ui.ime import ImeCursor, InputMethodBridge
from czero_apps.system.single_instance import run_single_instance

APP_ID = "dev.cardputerzero.defaultapps.terminal"
GLib.set_prgname(APP_ID)
GLib.set_application_name("Terminal")

WIDTH = 320
HEIGHT = 170
TAB_H = 20
TERM_H = 130
BOTTOM_H = 20
TERM_X = 4
TERM_Y = 22
TERM_W = 312
TERM_H_INNER = 126
TERM_PAD_X = 4
TERM_PAD_Y = 4
CELL_W = 6
CELL_H = 10
FONT_SIZE = 8
COLS = (TERM_W - TERM_PAD_X * 2) // CELL_W
ROWS = (TERM_H_INNER - TERM_PAD_Y * 2) // CELL_H

ZERO_PAPER = "#E9E4D5"
PANEL_CREAM = "#F4F0E6"
ICON_WELL = "#F8F4EA"
INK_BLACK = "#171717"
LINE_BLACK = "#2A2A2A"
MUTED_TEXT = "#6E6A61"
ACCENT_ORANGE = "#E66A2C"
OK_GREEN = "#3A7D44"
WARN_RED = "#B94A2C"
HARD_SHADOW = "#BDB5A4"
TERM_BG = "#171717"
TERM_FG = "#F4F0E6"
TERM_GREEN = "#9AD46A"
TERM_BLUE = "#6FA8DC"
TERM_RED = "#E35B4F"
TERM_YELLOW = "#EBCB5A"
TERM_CYAN = "#6FCBCB"
TERM_MUTED = "#8C887E"

ANSI_16 = [
    "#171717",
    TERM_RED,
    TERM_GREEN,
    TERM_YELLOW,
    TERM_BLUE,
    "#B070C0",
    TERM_CYAN,
    TERM_FG,
    TERM_MUTED,
    "#F07070",
    "#B8F080",
    "#F6D878",
    "#8FC4F0",
    "#D090E0",
    "#86E0E0",
    "#FFFFFF",
]

DEFAULT_CONFIG = {
    "font_family": "monospace",
    "font_size": FONT_SIZE,
    "scrollback_lines": 1000,
    "default_cwd": "home",
    "confirm_close_running_tabs": True,
    "inherit_cwd_for_new_tab": True,
    "show_tab_close_button": True,
    "max_visible_tabs": 3,
    "theme": "zero-paper-terminal",
}


def config_path() -> Path:
    return Path.home() / ".config" / "cardputer-zero" / "default-apps" / "terminal.json"


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
        try:
            path.replace(path.with_suffix(".json.bak"))
        except OSError:
            pass
        save_config(dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def shell_path() -> str | None:
    for candidate in (os.environ.get("SHELL", ""), "/bin/bash", "/bin/sh"):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def cwd_title(path: str, home: str) -> str:
    if not path:
        return "~"
    try:
        resolved = str(Path(path).resolve())
        home_resolved = str(Path(home).resolve())
    except OSError:
        resolved = path
        home_resolved = home
    if resolved == home_resolved:
        return "~"
    if resolved.startswith(home_resolved + os.sep):
        return "~/" + resolved[len(home_resolved) + 1 :]
    return resolved


def fit_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 2:
        return value[:limit]
    return value[: limit - 2] + ".."


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)


def color(ctx, value: str) -> None:
    ctx.set_source_rgb(*hex_to_rgb(value))


def needs_shaped_text(value: str) -> bool:
    return any(ord(ch) > 127 for ch in value)


def pango_font(size: int, bold: bool = False) -> Pango.FontDescription:
    desc = Pango.FontDescription()
    desc.set_family("monospace, Noto Sans CJK SC, WenQuanYi Micro Hei, Sans")
    desc.set_size(size * Pango.SCALE)
    desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    return desc


def fill(ctx, x: int, y: int, w: int, h: int, value: str) -> None:
    color(ctx, value)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def stroke(ctx, x: int, y: int, w: int, h: int, value: str = LINE_BLACK) -> None:
    color(ctx, value)
    ctx.set_line_width(1)
    ctx.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
    ctx.stroke()


def line(ctx, x1: int, y1: int, x2: int, y2: int, value: str = LINE_BLACK) -> None:
    color(ctx, value)
    ctx.set_line_width(1)
    ctx.move_to(x1 + 0.5, y1 + 0.5)
    ctx.line_to(x2 + 0.5, y2 + 0.5)
    ctx.stroke()


def draw_text(ctx, value: str, x: int, y: int, fg: str = INK_BLACK, size: int = 8, bold: bool = False) -> None:
    color(ctx, fg)
    if needs_shaped_text(value):
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(pango_font(size, bold))
        layout.set_text(value, -1)
        ctx.move_to(x, y - size)
        PangoCairo.show_layout(ctx, layout)
        return
    ctx.select_font_face("monospace", 0, 1 if bold else 0)
    ctx.set_font_size(size)
    ctx.move_to(x, y)
    ctx.show_text(value)


def draw_key(ctx, x: int, y: int, label: str, w: int) -> None:
    fill(ctx, x + 1, y + 13, w, 2, HARD_SHADOW)
    fill(ctx, x, y, w, 14, ICON_WELL)
    stroke(ctx, x, y, w, 15)
    line(ctx, x + 2, y + 11, x + w - 3, y + 11)
    draw_text(ctx, label, x + 4, y + 10, INK_BLACK, 8, True)


@dataclass
class Attr:
    fg: str = TERM_FG
    bg: str = TERM_BG
    bold: bool = False
    inverse: bool = False

    def copy(self) -> "Attr":
        return Attr(self.fg, self.bg, self.bold, self.inverse)


@dataclass
class Cell:
    ch: str = " "
    attr: Attr = field(default_factory=Attr)

    def copy(self) -> "Cell":
        return Cell(self.ch, self.attr.copy())


class TerminalScreen:
    def __init__(self, cols: int, rows: int, scrollback_limit: int = 1000) -> None:
        self.cols = cols
        self.rows = rows
        self.scrollback_limit = scrollback_limit
        self.scrollback: list[list[Cell]] = []
        self.attr = Attr()
        self.lines = self.blank_lines()
        self.alt_lines: list[list[Cell]] | None = None
        self.alt_scrollback: list[list[Cell]] | None = None
        self.cursor_row = 0
        self.cursor_col = 0
        self.saved_cursor = (0, 0, self.attr.copy())
        self.scroll_top = 0
        self.scroll_bottom = rows - 1
        self.wrap = True
        self.cursor_visible = True
        self.alt_screen = False
        self.dirty_title = ""

    def blank_cell(self) -> Cell:
        return Cell(" ", self.attr.copy())

    def blank_line(self) -> list[Cell]:
        return [self.blank_cell() for _ in range(self.cols)]

    def blank_lines(self) -> list[list[Cell]]:
        return [self.blank_line() for _ in range(self.rows)]

    def reset(self) -> None:
        self.attr = Attr()
        self.lines = self.blank_lines()
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.wrap = True
        self.cursor_visible = True

    def clamp_cursor(self) -> None:
        self.cursor_row = max(0, min(self.cursor_row, self.rows - 1))
        self.cursor_col = max(0, min(self.cursor_col, self.cols - 1))

    def save_cursor(self) -> None:
        self.saved_cursor = (self.cursor_row, self.cursor_col, self.attr.copy())

    def restore_cursor(self) -> None:
        self.cursor_row, self.cursor_col, self.attr = self.saved_cursor[0], self.saved_cursor[1], self.saved_cursor[2].copy()
        self.clamp_cursor()

    def set_cursor(self, row: int, col: int) -> None:
        self.cursor_row = max(0, min(row, self.rows - 1))
        self.cursor_col = max(0, min(col, self.cols - 1))

    def scroll_up(self, count: int = 1) -> None:
        for _ in range(max(1, count)):
            removed = self.lines.pop(self.scroll_top)
            if not self.alt_screen and self.scroll_top == 0:
                self.scrollback.append([cell.copy() for cell in removed])
                if len(self.scrollback) > self.scrollback_limit:
                    self.scrollback = self.scrollback[-self.scrollback_limit :]
            self.lines.insert(self.scroll_bottom, self.blank_line())

    def scroll_down(self, count: int = 1) -> None:
        for _ in range(max(1, count)):
            self.lines.pop(self.scroll_bottom)
            self.lines.insert(self.scroll_top, self.blank_line())

    def linefeed(self) -> None:
        if self.cursor_row == self.scroll_bottom:
            self.scroll_up()
        else:
            self.cursor_row = min(self.cursor_row + 1, self.rows - 1)

    def reverse_index(self) -> None:
        if self.cursor_row == self.scroll_top:
            self.scroll_down()
        else:
            self.cursor_row = max(self.cursor_row - 1, 0)

    def put_char(self, ch: str) -> None:
        if len(ch) != 1:
            return
        self.lines[self.cursor_row][self.cursor_col] = Cell(ch, self.attr.copy())
        if self.cursor_col == self.cols - 1:
            if self.wrap:
                self.cursor_col = 0
                self.linefeed()
        else:
            self.cursor_col += 1

    def tab(self) -> None:
        self.cursor_col = min(((self.cursor_col // 8) + 1) * 8, self.cols - 1)

    def backspace(self) -> None:
        self.cursor_col = max(0, self.cursor_col - 1)

    def clear_line(self, mode: int) -> None:
        if mode == 0:
            start, end = self.cursor_col, self.cols
        elif mode == 1:
            start, end = 0, self.cursor_col + 1
        else:
            start, end = 0, self.cols
        for col in range(start, end):
            self.lines[self.cursor_row][col] = self.blank_cell()

    def clear_screen(self, mode: int) -> None:
        if mode == 2 or mode == 3:
            self.lines = self.blank_lines()
            if mode == 3:
                self.scrollback.clear()
            self.set_cursor(0, 0)
            return
        if mode == 0:
            self.clear_line(0)
            for row in range(self.cursor_row + 1, self.rows):
                self.lines[row] = self.blank_line()
        elif mode == 1:
            for row in range(0, self.cursor_row):
                self.lines[row] = self.blank_line()
            self.clear_line(1)

    def insert_chars(self, count: int) -> None:
        count = max(1, count)
        row = self.lines[self.cursor_row]
        for _ in range(count):
            row.insert(self.cursor_col, self.blank_cell())
            row.pop()

    def delete_chars(self, count: int) -> None:
        count = max(1, count)
        row = self.lines[self.cursor_row]
        for _ in range(count):
            if self.cursor_col < len(row):
                row.pop(self.cursor_col)
                row.append(self.blank_cell())

    def erase_chars(self, count: int) -> None:
        for col in range(self.cursor_col, min(self.cursor_col + max(1, count), self.cols)):
            self.lines[self.cursor_row][col] = self.blank_cell()

    def insert_lines(self, count: int) -> None:
        if not (self.scroll_top <= self.cursor_row <= self.scroll_bottom):
            return
        for _ in range(max(1, count)):
            self.lines.insert(self.cursor_row, self.blank_line())
            self.lines.pop(self.scroll_bottom + 1)

    def delete_lines(self, count: int) -> None:
        if not (self.scroll_top <= self.cursor_row <= self.scroll_bottom):
            return
        for _ in range(max(1, count)):
            self.lines.pop(self.cursor_row)
            self.lines.insert(self.scroll_bottom, self.blank_line())

    def set_scroll_region(self, top: int, bottom: int) -> None:
        top = max(0, min(top, self.rows - 1))
        bottom = max(0, min(bottom, self.rows - 1))
        if top < bottom:
            self.scroll_top = top
            self.scroll_bottom = bottom
            self.set_cursor(0, 0)

    def use_alt_screen(self, enabled: bool) -> None:
        if enabled == self.alt_screen:
            return
        if enabled:
            self.alt_lines = self.lines
            self.alt_scrollback = self.scrollback
            self.lines = self.blank_lines()
            self.scrollback = []
            self.alt_screen = True
            self.set_cursor(0, 0)
        else:
            if self.alt_lines is not None:
                self.lines = self.alt_lines
            if self.alt_scrollback is not None:
                self.scrollback = self.alt_scrollback
            self.alt_lines = None
            self.alt_scrollback = None
            self.alt_screen = False
            self.set_cursor(0, 0)

    def apply_sgr(self, params: list[int]) -> None:
        if not params:
            params = [0]
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self.attr = Attr()
            elif p == 1:
                self.attr.bold = True
            elif p in (2, 22):
                self.attr.bold = False
            elif p == 7:
                self.attr.inverse = True
            elif p == 27:
                self.attr.inverse = False
            elif p == 39:
                self.attr.fg = TERM_FG
            elif p == 49:
                self.attr.bg = TERM_BG
            elif 30 <= p <= 37:
                self.attr.fg = ANSI_16[p - 30]
            elif 90 <= p <= 97:
                self.attr.fg = ANSI_16[p - 90 + 8]
            elif 40 <= p <= 47:
                self.attr.bg = ANSI_16[p - 40]
            elif 100 <= p <= 107:
                self.attr.bg = ANSI_16[p - 100 + 8]
            elif p in (38, 48):
                is_fg = p == 38
                if i + 2 < len(params) and params[i + 1] == 5:
                    mapped = xterm_256(params[i + 2])
                    if is_fg:
                        self.attr.fg = mapped
                    else:
                        self.attr.bg = mapped
                    i += 2
                elif i + 4 < len(params) and params[i + 1] == 2:
                    mapped = f"#{params[i + 2] & 255:02X}{params[i + 3] & 255:02X}{params[i + 4] & 255:02X}"
                    if is_fg:
                        self.attr.fg = mapped
                    else:
                        self.attr.bg = mapped
                    i += 4
            i += 1


def xterm_256(index: int) -> str:
    index = max(0, min(255, index))
    if index < 16:
        return ANSI_16[index]
    if 16 <= index <= 231:
        value = index - 16
        r = value // 36
        g = (value % 36) // 6
        b = value % 6
        conv = [0, 95, 135, 175, 215, 255]
        return f"#{conv[r]:02X}{conv[g]:02X}{conv[b]:02X}"
    shade = 8 + (index - 232) * 10
    return f"#{shade:02X}{shade:02X}{shade:02X}"


class AnsiParser:
    def __init__(self, screen: TerminalScreen, respond, title_callback) -> None:
        self.screen = screen
        self.respond = respond
        self.title_callback = title_callback
        self.state = "ground"
        self.buf = ""
        self.osc = ""
        self.charset_skip = False

    def feed(self, text: str) -> None:
        for ch in text:
            self.feed_char(ch)

    def feed_char(self, ch: str) -> None:
        if self.charset_skip:
            self.charset_skip = False
            self.state = "ground"
            return
        if self.state == "ground":
            self.ground(ch)
        elif self.state == "esc":
            self.escape(ch)
        elif self.state == "csi":
            self.csi(ch)
        elif self.state == "osc":
            self.osc_feed(ch)

    def ground(self, ch: str) -> None:
        code = ord(ch)
        if ch == "\x1b":
            self.state = "esc"
        elif ch == "\n":
            self.screen.linefeed()
        elif ch == "\r":
            self.screen.cursor_col = 0
        elif ch == "\b":
            self.screen.backspace()
        elif ch == "\t":
            self.screen.tab()
        elif ch == "\x0f" or ch == "\x0e":
            pass
        elif ch == "\x07":
            pass
        elif code >= 0x20:
            self.screen.put_char(ch)

    def escape(self, ch: str) -> None:
        self.state = "ground"
        if ch == "[":
            self.buf = ""
            self.state = "csi"
        elif ch == "]":
            self.osc = ""
            self.state = "osc"
        elif ch in "()#%":
            self.charset_skip = True
        elif ch == "7":
            self.screen.save_cursor()
        elif ch == "8":
            self.screen.restore_cursor()
        elif ch == "D":
            self.screen.linefeed()
        elif ch == "E":
            self.screen.cursor_col = 0
            self.screen.linefeed()
        elif ch == "M":
            self.screen.reverse_index()
        elif ch == "c":
            self.screen.reset()

    def osc_feed(self, ch: str) -> None:
        if ch == "\x07":
            self.handle_osc(self.osc)
            self.state = "ground"
        elif ch == "\x1b":
            self.state = "osc-esc"
        else:
            self.osc += ch
            if len(self.osc) > 1024:
                self.state = "ground"

    def csi(self, ch: str) -> None:
        if "@" <= ch <= "~":
            self.handle_csi(self.buf, ch)
            self.buf = ""
            self.state = "ground"
        else:
            self.buf += ch
            if len(self.buf) > 128:
                self.buf = ""
                self.state = "ground"

    def handle_osc(self, value: str) -> None:
        if ";" not in value:
            return
        kind, content = value.split(";", 1)
        if kind in ("0", "1", "2"):
            title = content.strip()
            if title:
                self.title_callback(title)

    def parse_params(self, raw: str) -> tuple[str, list[int]]:
        private = ""
        while raw and raw[0] in "?=>!":
            private += raw[0]
            raw = raw[1:]
        if not raw:
            return private, []
        params = []
        for part in raw.split(";"):
            if part == "":
                params.append(0)
            else:
                try:
                    params.append(int(part))
                except ValueError:
                    params.append(0)
        return private, params

    def p(self, params: list[int], index: int, default: int = 1) -> int:
        if index >= len(params) or params[index] == 0:
            return default
        return params[index]

    def handle_csi(self, raw: str, final: str) -> None:
        private, params = self.parse_params(raw)
        s = self.screen
        if final == "A":
            s.cursor_row -= self.p(params, 0)
        elif final == "B":
            s.cursor_row += self.p(params, 0)
        elif final == "C":
            s.cursor_col += self.p(params, 0)
        elif final == "D":
            s.cursor_col -= self.p(params, 0)
        elif final == "E":
            s.cursor_row += self.p(params, 0)
            s.cursor_col = 0
        elif final == "F":
            s.cursor_row -= self.p(params, 0)
            s.cursor_col = 0
        elif final == "G":
            s.cursor_col = self.p(params, 0) - 1
        elif final in ("H", "f"):
            s.set_cursor(self.p(params, 0) - 1, self.p(params, 1) - 1)
            return
        elif final == "J":
            s.clear_screen(self.p(params, 0, 0))
            return
        elif final == "K":
            s.clear_line(self.p(params, 0, 0))
            return
        elif final == "L":
            s.insert_lines(self.p(params, 0))
            return
        elif final == "M":
            s.delete_lines(self.p(params, 0))
            return
        elif final == "@":
            s.insert_chars(self.p(params, 0))
            return
        elif final == "P":
            s.delete_chars(self.p(params, 0))
            return
        elif final == "X":
            s.erase_chars(self.p(params, 0))
            return
        elif final == "m":
            s.apply_sgr(params)
            return
        elif final == "r":
            top = self.p(params, 0, 1) - 1
            bottom = self.p(params, 1, s.rows) - 1
            s.set_scroll_region(top, bottom)
            return
        elif final == "s":
            s.save_cursor()
            return
        elif final == "u":
            s.restore_cursor()
            return
        elif final == "n" and self.p(params, 0) == 6:
            self.respond(f"\x1b[{s.cursor_row + 1};{s.cursor_col + 1}R".encode())
            return
        elif final in ("h", "l"):
            self.handle_mode(private, params, final == "h")
            return
        s.clamp_cursor()

    def handle_mode(self, private: str, params: list[int], enabled: bool) -> None:
        for param in params:
            if private == "?":
                if param in (47, 1047, 1049):
                    self.screen.use_alt_screen(enabled)
                elif param == 25:
                    self.screen.cursor_visible = enabled
                elif param == 7:
                    self.screen.wrap = enabled


@dataclass
class ClosedTabInfo:
    title: str
    cwd: str
    closed_at: float


class TerminalTab:
    def __init__(self, tab_id: int, cwd: str, title: str, config: dict, on_output, on_exit, on_title) -> None:
        self.id = tab_id
        self.cwd = cwd
        self.title = title
        self.custom_title: str | None = None
        self.exited = False
        self.process: subprocess.Popen | None = None
        self.master_fd: int | None = None
        self.watch_id: int | None = None
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.screen = TerminalScreen(COLS, ROWS, int(config.get("scrollback_lines", 1000)))
        self.parser = AnsiParser(self.screen, self.write, on_title)
        self.on_output = on_output
        self.on_exit = on_exit

    def start(self, shell: str) -> None:
        master, slave = pty.openpty()
        self.master_fd = master
        os.set_blocking(master, False)
        set_pty_size(master, ROWS, COLS)
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env.setdefault("LINES", str(ROWS))
        env.setdefault("COLUMNS", str(COLS))
        self.process = subprocess.Popen(
            [shell],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=self.cwd,
            env=env,
            close_fds=True,
            preexec_fn=os.setsid,
        )
        os.close(slave)
        self.watch_id = GLib.io_add_watch(master, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.read_ready)
        GLib.child_watch_add(self.process.pid, self.child_exited)

    def read_ready(self, fd: int, condition: GLib.IOCondition) -> bool:
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            return False
        try:
            data = os.read(fd, 8192)
        except BlockingIOError:
            return True
        except OSError:
            return False
        if not data:
            return False
        text = self.decoder.decode(data)
        self.parser.feed(text)
        self.refresh_cwd()
        self.on_output(self)
        return True

    def child_exited(self, _pid: int, _status: int) -> None:
        self.exited = True
        self.on_exit(self)

    def write(self, data: bytes) -> None:
        if self.master_fd is None:
            return
        try:
            os.write(self.master_fd, data)
        except OSError:
            pass

    def refresh_cwd(self) -> None:
        if not self.process:
            return
        try:
            cwd = str((Path("/proc") / str(self.process.pid) / "cwd").resolve())
        except OSError:
            return
        if cwd:
            self.cwd = cwd

    def close(self) -> None:
        if self.watch_id:
            GLib.source_remove(self.watch_id)
            self.watch_id = None
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGHUP)
            except OSError:
                try:
                    self.process.terminate()
                except OSError:
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None


def set_pty_size(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


class TerminalCanvas(Gtk.DrawingArea):
    def __init__(self, window: "TerminalWindow") -> None:
        super().__init__()
        self.window = window
        self.set_size_request(WIDTH, HEIGHT)
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("draw", self.draw)
        self.connect("key-press-event", window.on_key_press)
        self.connect("button-press-event", self.on_click)

    def draw(self, _widget, ctx) -> bool:
        ctx.set_antialias(0)
        fill(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
        self.draw_tabbar(ctx)
        self.draw_terminal(ctx)
        self.draw_bottom(ctx)
        self.draw_overlay(ctx)
        return True

    def draw_tabbar(self, ctx) -> None:
        fill(ctx, 0, 0, WIDTH, TAB_H, ZERO_PAPER)
        tabs = self.window.tabs
        start, end = self.window.visible_tab_range()
        x = 4
        tab_w = 86
        for index in range(start, end):
            tab = tabs[index]
            selected = index == self.window.active_index
            fill(ctx, x, 2, tab_w, 16, ICON_WELL if selected else PANEL_CREAM)
            stroke(ctx, x, 2, tab_w, 16, ACCENT_ORANGE if selected else LINE_BLACK)
            label = f"{tab.id} {fit_text(tab.title, 8)}"
            draw_text(ctx, label, x + 5, 13, ACCENT_ORANGE if selected else INK_BLACK, 8, selected)
            draw_text(ctx, "x", x + tab_w - 11, 13, MUTED_TEXT, 8, True)
            x += tab_w + 3
        line(ctx, 0, TAB_H - 1, WIDTH, TAB_H - 1)

    def draw_terminal(self, ctx) -> None:
        fill(ctx, TERM_X + 2, TERM_Y + 2, TERM_W, TERM_H_INNER, HARD_SHADOW)
        fill(ctx, TERM_X, TERM_Y, TERM_W, TERM_H_INNER, TERM_BG)
        stroke(ctx, TERM_X, TERM_Y, TERM_W, TERM_H_INNER, LINE_BLACK)
        tab = self.window.active_tab()
        if not tab:
            draw_text(ctx, "No terminal tab", TERM_X + 8, TERM_Y + 18, TERM_FG, 8)
            return
        lines = self.window.visible_lines(tab)
        base_x = TERM_X + TERM_PAD_X
        base_y = TERM_Y + TERM_PAD_Y
        for row, row_cells in enumerate(lines[:ROWS]):
            for col, cell in enumerate(row_cells[:COLS]):
                fg = cell.attr.bg if cell.attr.inverse else cell.attr.fg
                bg = cell.attr.fg if cell.attr.inverse else cell.attr.bg
                x = base_x + col * CELL_W
                y = base_y + row * CELL_H
                if bg != TERM_BG:
                    fill(ctx, x, y, CELL_W, CELL_H, bg)
                if cell.ch != " ":
                    draw_text(ctx, cell.ch, x, y + 8, fg, FONT_SIZE, cell.attr.bold)
        if tab.screen.cursor_visible and self.window.scroll_offset == 0 and not tab.exited:
            cx = base_x + tab.screen.cursor_col * CELL_W
            cy = base_y + tab.screen.cursor_row * CELL_H
            fill(ctx, cx, cy + CELL_H - 2, CELL_W, 2, ACCENT_ORANGE)
            if self.window.im_preedit and not self.window.rename_mode:
                draw_text(ctx, fit_text(self.window.im_preedit, 20), cx, cy + 8, ACCENT_ORANGE, FONT_SIZE, True)
        if self.window.scroll_offset:
            draw_text(ctx, f"SCROLL {self.window.scroll_offset}", TERM_X + TERM_W - 70, TERM_Y + 12, TERM_YELLOW, 8, True)
        if tab.exited:
            draw_text(ctx, "session exited", TERM_X + TERM_W - 92, TERM_Y + TERM_H_INNER - 8, TERM_RED, 8, True)

    def draw_bottom(self, ctx) -> None:
        y = 150
        fill(ctx, 0, y, WIDTH, BOTTOM_H, ZERO_PAPER)
        line(ctx, 0, y, WIDTH, y)
        draw_key(ctx, 4, y + 3, "C+T", 27)
        draw_text(ctx, "New", 36, y + 13, INK_BLACK, 8)
        draw_key(ctx, 65, y + 3, "Alt", 28)
        draw_text(ctx, "<>", 99, y + 13, INK_BLACK, 8)
        draw_key(ctx, 135, y + 3, "C+W", 29)
        draw_text(ctx, "Close", 169, y + 13, INK_BLACK, 8)
        draw_key(ctx, 236, y + 3, "C+M", 30)
        draw_text(ctx, "Menu", 271, y + 13, INK_BLACK, 8)

    def draw_overlay(self, ctx) -> None:
        if self.window.error_text and time.monotonic() < self.window.error_until:
            self.panel(ctx, 16, 28, 288, 20, WARN_RED)
            draw_text(ctx, fit_text(self.window.error_text, 38), 24, 42, WARN_RED, 8, True)
        if self.window.menu_open:
            self.draw_menu(ctx)
        if self.window.tab_picker_mode:
            self.draw_tab_picker(ctx)
        if self.window.rename_mode:
            self.draw_input(ctx)
        if self.window.confirm_mode:
            self.draw_confirm(ctx)

    def panel(self, ctx, x: int, y: int, w: int, h: int, border: str = LINE_BLACK) -> None:
        fill(ctx, x + 2, y + 2, w, h, HARD_SHADOW)
        fill(ctx, x, y, w, h, PANEL_CREAM)
        stroke(ctx, x, y, w, h, border)

    def draw_menu(self, ctx) -> None:
        x, y, w, h = 82, 28, 156, 91
        self.panel(ctx, x, y, w, h)
        for index, label in enumerate(self.window.menu_items):
            row_y = y + 14 + index * 9
            selected = index == self.window.menu_index
            if selected:
                fill(ctx, x + 5, row_y - 8, w - 10, 9, ICON_WELL)
                stroke(ctx, x + 5, row_y - 8, w - 10, 9, ACCENT_ORANGE)
            draw_text(ctx, fit_text(label, 18), x + 12, row_y, ACCENT_ORANGE if selected else INK_BLACK, 8, selected)

    def draw_tab_picker(self, ctx) -> None:
        x, y, w = 52, 28, 216
        visible = min(5, max(1, len(self.window.tabs)))
        h = 30 + visible * 14
        self.panel(ctx, x, y, w, h)
        draw_text(ctx, "Switch Tab", x + 8, y + 14, ACCENT_ORANGE, 9, True)
        start = max(0, min(self.window.tab_picker_index - 2, max(0, len(self.window.tabs) - visible)))
        for offset, index in enumerate(range(start, min(len(self.window.tabs), start + visible))):
            tab = self.window.tabs[index]
            row_y = y + 30 + offset * 14
            selected = index == self.window.tab_picker_index
            if selected:
                fill(ctx, x + 6, row_y - 10, w - 12, 13, ICON_WELL)
                stroke(ctx, x + 6, row_y - 10, w - 12, 13, ACCENT_ORANGE)
            mark = "*" if index == self.window.active_index else " "
            draw_text(ctx, f"{mark}{tab.id}", x + 12, row_y, ACCENT_ORANGE if selected else INK_BLACK, 8, selected)
            draw_text(ctx, fit_text(tab.title, 23), x + 40, row_y, ACCENT_ORANGE if selected else INK_BLACK, 8, selected)

    def draw_input(self, ctx) -> None:
        x, y, w, h = 44, 42, 232, 58
        self.panel(ctx, x, y, w, h)
        draw_text(ctx, "Rename Tab", x + 9, y + 14, ACCENT_ORANGE, 9, True)
        fill(ctx, x + 9, y + 24, w - 18, 20, ICON_WELL)
        stroke(ctx, x + 9, y + 24, w - 18, 20, ACCENT_ORANGE)
        draw_text(ctx, fit_text(self.window.rename_text + self.window.im_preedit, 26), x + 15, y + 38, INK_BLACK, 9)
        draw_text(ctx, "Enter Apply   Esc Cancel", x + 9, y + 53, MUTED_TEXT, 8)

    def draw_confirm(self, ctx) -> None:
        x, y, w, h = 44, 42, 232, 58
        self.panel(ctx, x, y, w, h)
        draw_text(ctx, self.window.confirm_title, x + 9, y + 15, WARN_RED, 9, True)
        draw_text(ctx, fit_text(self.window.confirm_message, 28), x + 9, y + 31, INK_BLACK, 8)
        for index, label in enumerate(("Cancel", "Close")):
            bx = x + 45 + index * 78
            selected = index == self.window.confirm_index
            stroke_color = WARN_RED if selected and index else ACCENT_ORANGE if selected else LINE_BLACK
            fill(ctx, bx, y + 39, 60, 14, ICON_WELL)
            stroke(ctx, bx, y + 39, 60, 14, stroke_color)
            draw_text(ctx, label, bx + 10, y + 50, stroke_color if selected else INK_BLACK, 8, selected)

    def on_click(self, _widget, event) -> bool:
        self.grab_focus()
        if event.y < TAB_H:
            start, end = self.window.visible_tab_range()
            x = 4
            for index in range(start, end):
                if x <= event.x <= x + 86:
                    if event.x >= x + 69:
                        self.window.close_tab(index=index)
                    else:
                        self.window.switch_to(index)
                    return True
                x += 89
        return True


class TerminalWindow(Gtk.ApplicationWindow):
    menu_items = ("New Tab", "Switch Tab", "Close Tab", "Reopen Tab", "Rename Tab", "Copy", "Paste", "Clear", "Exit")

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Terminal")
        self.config = load_config()
        self.tabs: list[TerminalTab] = []
        self.closed_tabs: list[ClosedTabInfo] = []
        self.active_index = 0
        self.next_tab_id = 1
        self.home = str(Path.home())
        self.scroll_offset = 0
        self.error_text = ""
        self.error_until = 0.0
        self.menu_open = False
        self.menu_index = 0
        self.tab_picker_mode = False
        self.tab_picker_index = 0
        self.rename_mode = False
        self.rename_text = ""
        self.confirm_mode = False
        self.confirm_index = 0
        self.confirm_title = ""
        self.confirm_message = ""
        self.confirm_action = ""
        self.im_preedit = ""

        self.set_default_size(WIDTH, HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_role("zero-terminal")
        try:
            self.set_wmclass("zero-terminal", "ZeroTerminal")
        except AttributeError:
            pass
        self.connect("delete-event", self.on_delete)
        self.canvas = TerminalCanvas(self)
        self.add(self.canvas)
        self.canvas.show()
        self.ime = InputMethodBridge(
            self.canvas,
            self.ime_text,
            self.ime_cursor,
            self.on_ime_commit,
            self.on_ime_preedit,
        )
        self.add_terminal_accelerators()
        self.new_tab()
        GLib.timeout_add(1000, self.refresh_tab_titles)

    def ime_text(self) -> str:
        if self.rename_mode:
            return self.rename_text
        return ""

    def ime_cursor(self) -> ImeCursor:
        if self.rename_mode:
            x = 59 + min(len(self.rename_text), 26) * CELL_W
            return ImeCursor(x=x, y=68, height=12)
        tab = self.active_tab()
        if tab and self.scroll_offset == 0:
            x = TERM_X + TERM_PAD_X + tab.screen.cursor_col * CELL_W
            y = TERM_Y + TERM_PAD_Y + tab.screen.cursor_row * CELL_H
            return ImeCursor(x=x, y=y, width=CELL_W, height=CELL_H)
        return ImeCursor(x=TERM_X + TERM_PAD_X, y=TERM_Y + TERM_PAD_Y, width=CELL_W, height=CELL_H)

    def on_ime_commit(self, text_value: str) -> None:
        if not text_value:
            return
        if self.rename_mode:
            self.rename_text = (self.rename_text + text_value)[:32]
            self.ime.update()
            self.canvas.queue_draw()
            return
        self.scroll_offset = 0
        self.feed_active(text_value.encode("utf-8"))

    def on_ime_preedit(self, preedit: str) -> None:
        self.im_preedit = preedit
        self.canvas.queue_draw()

    def add_terminal_accelerators(self) -> None:
        accel_group = Gtk.AccelGroup()
        self.add_accel_group(accel_group)
        bindings = (
            ("t", Gdk.ModifierType.CONTROL_MASK, self.accel_new_tab),
            ("w", Gdk.ModifierType.CONTROL_MASK, self.accel_close_tab),
            ("m", Gdk.ModifierType.CONTROL_MASK, self.accel_menu),
            ("T", Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, self.accel_reopen_tab),
            ("R", Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, self.accel_rename_tab),
            ("Left", Gdk.ModifierType.MOD1_MASK, self.accel_prev_tab),
            ("Right", Gdk.ModifierType.MOD1_MASK, self.accel_next_tab),
        )
        for key_name, modifiers, callback in bindings:
            keyval = Gdk.keyval_from_name(key_name)
            if keyval:
                accel_group.connect(keyval, modifiers, Gtk.AccelFlags.VISIBLE, callback)
        self.accel_group = accel_group

    def accel_new_tab(self, *_args) -> bool:
        self.new_tab()
        return True

    def accel_close_tab(self, *_args) -> bool:
        self.close_tab()
        return True

    def accel_menu(self, *_args) -> bool:
        self.open_menu()
        return True

    def accel_reopen_tab(self, *_args) -> bool:
        self.reopen_tab()
        return True

    def accel_rename_tab(self, *_args) -> bool:
        self.rename_tab()
        return True

    def accel_prev_tab(self, *_args) -> bool:
        self.switch_relative(-1)
        return True

    def accel_next_tab(self, *_args) -> bool:
        self.switch_relative(1)
        return True

    def show_error(self, message: str) -> None:
        self.error_text = message
        self.error_until = time.monotonic() + 4.0
        self.canvas.queue_draw()

    def active_tab(self) -> TerminalTab | None:
        if not self.tabs:
            return None
        return self.tabs[self.active_index]

    def visible_tab_range(self) -> tuple[int, int]:
        total = len(self.tabs)
        max_visible = int(self.config.get("max_visible_tabs", 3))
        if total <= max_visible:
            return 0, total
        start = max(0, min(self.active_index - 1, total - max_visible))
        return start, start + max_visible

    def visible_lines(self, tab: TerminalTab) -> list[list[Cell]]:
        if self.scroll_offset <= 0 or tab.screen.alt_screen:
            return tab.screen.lines
        history = tab.screen.scrollback + tab.screen.lines
        start = max(0, len(history) - ROWS - self.scroll_offset)
        chunk = history[start : start + ROWS]
        while len(chunk) < ROWS:
            chunk.insert(0, tab.screen.blank_line())
        return chunk

    def new_tab(self, cwd: str | None = None, title: str | None = None) -> None:
        shell = shell_path()
        if not shell:
            self.show_error("Shell not found")
            return
        if cwd is None:
            active = self.active_tab()
            cwd = active.cwd if active and self.config.get("inherit_cwd_for_new_tab", True) else self.home
        tab = TerminalTab(
            self.next_tab_id,
            cwd,
            title or cwd_title(cwd, self.home),
            self.config,
            self.on_tab_output,
            self.on_tab_exit,
            lambda value: self.on_tab_title(tab, value) if "tab" in locals() else None,
        )
        self.next_tab_id += 1
        tab.custom_title = title
        self.tabs.append(tab)
        self.switch_to(len(self.tabs) - 1)
        try:
            tab.start(shell)
        except Exception as exc:
            self.show_error(f"Failed to start shell: {exc}")

    def on_tab_title(self, tab: TerminalTab, value: str) -> None:
        if not tab.custom_title:
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned:
                tab.title = fit_text(cleaned, 18)

    def on_tab_output(self, tab: TerminalTab) -> None:
        if tab is self.active_tab() and self.scroll_offset == 0:
            self.canvas.queue_draw()
        elif tab is self.active_tab():
            self.canvas.queue_draw()

    def on_tab_exit(self, tab: TerminalTab) -> None:
        if not tab.title.endswith(" done"):
            tab.title = fit_text(tab.title, 10) + " done"
        self.canvas.queue_draw()

    def refresh_tab_titles(self) -> bool:
        for tab in self.tabs:
            tab.refresh_cwd()
            if not tab.custom_title and not tab.exited:
                tab.title = cwd_title(tab.cwd, self.home)
        self.canvas.queue_draw()
        return True

    def switch_to(self, index: int) -> None:
        if not self.tabs:
            return
        self.active_index = max(0, min(index, len(self.tabs) - 1))
        self.scroll_offset = 0
        self.close_overlay_modes()
        self.canvas.grab_focus()
        self.canvas.queue_draw()

    def switch_relative(self, delta: int) -> None:
        if self.tabs:
            self.switch_to((self.active_index + delta) % len(self.tabs))

    def close_tab(self, force_app: bool = False, index: int | None = None) -> None:
        if not self.tabs:
            self.destroy()
            return
        close_index = self.active_index if index is None else max(0, min(index, len(self.tabs) - 1))
        if len(self.tabs) == 1 and not force_app:
            self.open_confirm("Close last tab?", "Close the terminal app?", "close-app")
            return
        tab = self.tabs.pop(close_index)
        self.closed_tabs.append(ClosedTabInfo(tab.custom_title or tab.title, tab.cwd, time.time()))
        tab.close()
        if not self.tabs:
            self.destroy()
            return
        if close_index < self.active_index:
            self.active_index -= 1
        elif close_index == self.active_index:
            self.active_index = min(close_index, len(self.tabs) - 1)
        self.switch_to(self.active_index)

    def reopen_tab(self) -> None:
        if not self.closed_tabs:
            self.show_error("No closed tab")
            return
        info = self.closed_tabs.pop()
        self.new_tab(info.cwd, info.title)

    def rename_tab(self) -> None:
        tab = self.active_tab()
        if not tab:
            return
        self.close_overlay_modes()
        self.rename_mode = True
        self.rename_text = tab.custom_title or tab.title
        self.canvas.queue_draw()

    def open_menu(self) -> None:
        self.close_overlay_modes()
        self.menu_open = True
        self.menu_index = 0
        self.canvas.queue_draw()

    def open_tab_picker(self) -> None:
        self.close_overlay_modes()
        self.tab_picker_mode = True
        self.tab_picker_index = self.active_index
        self.canvas.queue_draw()

    def open_confirm(self, title: str, message: str, action: str) -> None:
        self.close_overlay_modes()
        self.confirm_mode = True
        self.confirm_title = title
        self.confirm_message = message
        self.confirm_action = action
        self.confirm_index = 0
        self.canvas.queue_draw()

    def close_overlay_modes(self) -> None:
        self.menu_open = False
        self.tab_picker_mode = False
        self.rename_mode = False
        self.confirm_mode = False

    def menu_activate(self) -> None:
        label = self.menu_items[self.menu_index]
        if label == "New Tab":
            self.new_tab()
        elif label == "Switch Tab":
            self.open_tab_picker()
        elif label == "Close Tab":
            self.close_tab()
        elif label == "Reopen Tab":
            self.reopen_tab()
        elif label == "Rename Tab":
            self.rename_tab()
        elif label == "Copy":
            self.copy_visible()
            self.close_overlay_modes()
        elif label == "Paste":
            self.paste_clipboard()
            self.close_overlay_modes()
        elif label == "Clear":
            self.feed_active(b"\x0c")
            self.close_overlay_modes()
        elif label == "Exit":
            self.open_confirm("Close Terminal?", f"Close {len(self.tabs)} running tabs.", "exit")
        self.canvas.queue_draw()

    def copy_visible(self) -> None:
        tab = self.active_tab()
        if not tab:
            return
        text_value = "\n".join("".join(cell.ch for cell in row).rstrip() for row in self.visible_lines(tab))
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text_value, -1)

    def paste_clipboard(self) -> None:
        text_value = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        if text_value:
            self.feed_active(text_value.encode("utf-8"))

    def feed_active(self, data: bytes) -> None:
        tab = self.active_tab()
        if tab:
            tab.write(data)

    def scroll_history(self, delta: int) -> None:
        tab = self.active_tab()
        if not tab or tab.screen.alt_screen:
            return
        max_scroll = max(0, len(tab.screen.scrollback))
        self.scroll_offset = max(0, min(self.scroll_offset + delta, max_scroll))
        self.canvas.queue_draw()

    def handle_rename_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.ime.reset()
            self.close_overlay_modes()
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            tab = self.active_tab()
            if tab and self.rename_text.strip():
                tab.custom_title = self.rename_text.strip()
                tab.title = tab.custom_title
            self.ime.reset()
            self.close_overlay_modes()
        elif keyval == Gdk.KEY_BackSpace:
            self.rename_text = self.rename_text[:-1]
            self.ime.update()
        else:
            char = Gdk.keyval_to_unicode(keyval)
            if char and 32 <= char <= 126 and not (state & Gdk.ModifierType.CONTROL_MASK):
                self.rename_text = (self.rename_text + chr(char))[:32]
                self.ime.update()
        self.canvas.queue_draw()
        return True

    def handle_menu_key(self, keyval: int) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close_overlay_modes()
        elif keyval == Gdk.KEY_Down:
            self.menu_index = (self.menu_index + 1) % len(self.menu_items)
        elif keyval == Gdk.KEY_Up:
            self.menu_index = (self.menu_index - 1) % len(self.menu_items)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.menu_activate()
        self.canvas.queue_draw()
        return True

    def handle_tab_picker_key(self, keyval: int) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close_overlay_modes()
        elif keyval == Gdk.KEY_Down and self.tabs:
            self.tab_picker_index = (self.tab_picker_index + 1) % len(self.tabs)
        elif keyval == Gdk.KEY_Up and self.tabs:
            self.tab_picker_index = (self.tab_picker_index - 1) % len(self.tabs)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            target = self.tab_picker_index
            self.close_overlay_modes()
            self.switch_to(target)
        self.canvas.queue_draw()
        return True

    def handle_confirm_key(self, keyval: int) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close_overlay_modes()
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            self.confirm_index = 1 - self.confirm_index
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            action = self.confirm_action
            confirmed = self.confirm_index == 1
            self.close_overlay_modes()
            if confirmed:
                if action == "close-app":
                    self.close_tab(True)
                elif action == "exit":
                    self.destroy()
        self.canvas.queue_draw()
        return True

    def on_key_press(self, _widget, event) -> bool:
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(state & Gdk.ModifierType.MOD1_MASK)

        if self.rename_mode:
            if self.ime.filter_key_event(event):
                return True
            return self.handle_rename_key(event.keyval, state)
        if self.menu_open:
            return self.handle_menu_key(event.keyval)
        if self.tab_picker_mode:
            return self.handle_tab_picker_key(event.keyval)
        if self.confirm_mode:
            return self.handle_confirm_key(event.keyval)

        if ctrl and shift and event.keyval in (Gdk.KEY_T, Gdk.KEY_t):
            self.reopen_tab()
            return True
        if ctrl and shift and event.keyval in (Gdk.KEY_R, Gdk.KEY_r):
            self.rename_tab()
            return True
        if ctrl and event.keyval in (Gdk.KEY_T, Gdk.KEY_t):
            self.new_tab()
            return True
        if ctrl and event.keyval in (Gdk.KEY_W, Gdk.KEY_w):
            self.close_tab()
            return True
        if ctrl and event.keyval in (Gdk.KEY_M, Gdk.KEY_m):
            self.open_menu()
            return True
        if alt and event.keyval == Gdk.KEY_Left:
            self.switch_relative(-1)
            return True
        if alt and event.keyval == Gdk.KEY_Right:
            self.switch_relative(1)
            return True
        if shift and event.keyval in (Gdk.KEY_Up, Gdk.KEY_Page_Up):
            self.scroll_history(1 if event.keyval == Gdk.KEY_Up else ROWS)
            return True
        if shift and event.keyval in (Gdk.KEY_Down, Gdk.KEY_Page_Down):
            self.scroll_history(-1 if event.keyval == Gdk.KEY_Down else -ROWS)
            return True
        if not ctrl and not alt and key_is_text_input(event) and self.ime.filter_key_event(event):
            return True

        data = key_to_bytes(event)
        if data:
            self.scroll_offset = 0
            self.feed_active(data)
            return True
        return False

    def on_delete(self, _widget, _event) -> bool:
        for tab in list(self.tabs):
            tab.close()
        return False


def key_to_bytes(event) -> bytes | None:
    state = event.state
    ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
    alt = bool(state & Gdk.ModifierType.MOD1_MASK)
    keyval = event.keyval
    mapping = {
        Gdk.KEY_Return: b"\r",
        Gdk.KEY_KP_Enter: b"\r",
        Gdk.KEY_BackSpace: b"\x7f",
        Gdk.KEY_Tab: b"\t",
        Gdk.KEY_Escape: b"\x1b",
        Gdk.KEY_Up: b"\x1b[A",
        Gdk.KEY_Down: b"\x1b[B",
        Gdk.KEY_Right: b"\x1b[C",
        Gdk.KEY_Left: b"\x1b[D",
        Gdk.KEY_Home: b"\x1b[H",
        Gdk.KEY_End: b"\x1b[F",
        Gdk.KEY_Insert: b"\x1b[2~",
        Gdk.KEY_Delete: b"\x1b[3~",
        Gdk.KEY_Page_Up: b"\x1b[5~",
        Gdk.KEY_Page_Down: b"\x1b[6~",
        Gdk.KEY_F1: b"\x1bOP",
        Gdk.KEY_F2: b"\x1bOQ",
        Gdk.KEY_F3: b"\x1bOR",
        Gdk.KEY_F4: b"\x1bOS",
        Gdk.KEY_F5: b"\x1b[15~",
        Gdk.KEY_F6: b"\x1b[17~",
        Gdk.KEY_F7: b"\x1b[18~",
        Gdk.KEY_F8: b"\x1b[19~",
        Gdk.KEY_F9: b"\x1b[20~",
        Gdk.KEY_F10: b"\x1b[21~",
        Gdk.KEY_F11: b"\x1b[23~",
        Gdk.KEY_F12: b"\x1b[24~",
    }
    if keyval in mapping:
        data = mapping[keyval]
        return b"\x1b" + data if alt and data != b"\x1b" else data
    char = Gdk.keyval_to_unicode(keyval)
    if char:
        if ctrl and 64 <= char <= 95:
            return bytes([char - 64])
        if ctrl and 97 <= char <= 122:
            return bytes([char - 96])
        if not ctrl:
            data = chr(char).encode("utf-8")
            return b"\x1b" + data if alt else data
    return None


def key_is_text_input(event) -> bool:
    if event.keyval in {
        Gdk.KEY_Return,
        Gdk.KEY_KP_Enter,
        Gdk.KEY_BackSpace,
        Gdk.KEY_Tab,
        Gdk.KEY_Escape,
        Gdk.KEY_Up,
        Gdk.KEY_Down,
        Gdk.KEY_Right,
        Gdk.KEY_Left,
        Gdk.KEY_Home,
        Gdk.KEY_End,
        Gdk.KEY_Insert,
        Gdk.KEY_Delete,
        Gdk.KEY_Page_Up,
        Gdk.KEY_Page_Down,
    }:
        return False
    char = Gdk.keyval_to_unicode(event.keyval)
    return bool(char and char >= 32)


class TerminalApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: TerminalWindow | None = None

    def do_activate(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background: #E9E4D5; }")
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if self.window is None:
            self.window = TerminalWindow(self)
            self.window.connect("destroy", self.on_window_destroy)
        self.window.show_all()
        self.window.present()
        self.window.canvas.grab_focus()

    def on_window_destroy(self, _window) -> None:
        self.window = None


def run(argv: list[str] | None = None) -> int:
    return run_single_instance(APP_ID, lambda: TerminalApplication().run(argv or []))
