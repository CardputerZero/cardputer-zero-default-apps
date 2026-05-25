from __future__ import annotations

import math
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cairo

from czero_apps.system import files as file_backend
from czero_apps.ui.gtk import Gdk, Gtk


WIDTH = 320
HEIGHT = 170
MAIN_H = 150
BOTTOM_H = 20

PANEL_Y = 4
PANEL_H = 142
LEFT_X = 4
LEFT_W = 72
RIGHT_X = 80
RIGHT_W = 236
VISIBLE_ROWS = 7

ZERO_PAPER = (0xE9 / 255, 0xE4 / 255, 0xD5 / 255)
PANEL_CREAM = (0xF4 / 255, 0xF0 / 255, 0xE6 / 255)
ICON_WELL = (0xF8 / 255, 0xF4 / 255, 0xEA / 255)
INK_BLACK = (0x17 / 255, 0x17 / 255, 0x17 / 255)
LINE_BLACK = (0x2A / 255, 0x2A / 255, 0x2A / 255)
MUTED_TEXT = (0x6E / 255, 0x6A / 255, 0x61 / 255)
ACCENT_ORANGE = (0xE6 / 255, 0x6A / 255, 0x2C / 255)
WARN_RED = (0xB9 / 255, 0x4A / 255, 0x2C / 255)
HARD_SHADOW = (0xBD / 255, 0xB5 / 255, 0xA4 / 255)
SELECT_FILL = (0xFB / 255, 0xEE / 255, 0xDD / 255)
TITLE_FILL = (0xF0 / 255, 0xD2 / 255, 0xBD / 255)


@dataclass(frozen=True)
class FileItem:
    name: str
    path: Path
    icon: str
    size: str
    date: str
    is_dir: bool
    is_parent: bool = False
    is_current: bool = False


@dataclass(frozen=True)
class MenuAction:
    action_id: str
    label: str
    key: str


MENU_ACTIONS = [
    MenuAction("home", "HOME", "H"),
    MenuAction("new_folder", "NEW FOLDER", "N"),
    MenuAction("properties", "PROPERTIES", "P"),
]


def set_color(ctx: cairo.Context, color: tuple[float, float, float]) -> None:
    ctx.set_source_rgb(*color)


def crisp_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int) -> None:
    ctx.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)


def fill_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float]) -> None:
    set_color(ctx, color)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def stroke_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float]) -> None:
    set_color(ctx, color)
    ctx.set_line_width(1)
    crisp_rect(ctx, x, y, w, h)
    ctx.stroke()


def panel(ctx: cairo.Context, x: int, y: int, w: int, h: int) -> None:
    fill_rect(ctx, x + 2, y + 2, w, h, HARD_SHADOW)
    fill_rect(ctx, x, y, w, h, PANEL_CREAM)
    stroke_rect(ctx, x, y, w, h, LINE_BLACK)


def line(ctx: cairo.Context, x1: int, y1: int, x2: int, y2: int, color: tuple[float, float, float] = LINE_BLACK) -> None:
    set_color(ctx, color)
    ctx.set_line_width(1)
    ctx.move_to(x1 + 0.5, y1 + 0.5)
    ctx.line_to(x2 + 0.5, y2 + 0.5)
    ctx.stroke()


def configure_crisp(ctx: cairo.Context) -> None:
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_NONE)
    ctx.set_font_options(options)


def text(
    ctx: cairo.Context,
    value: str,
    x: int,
    y: int,
    color: tuple[float, float, float] = INK_BLACK,
    size: int = 10,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> None:
    set_color(ctx, color)
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    ctx.move_to(x, y)
    ctx.show_text(value)


def text_right(
    ctx: cairo.Context,
    value: str,
    right: int,
    y: int,
    color: tuple[float, float, float] = INK_BLACK,
    size: int = 10,
) -> None:
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ext = ctx.text_extents(value)
    text(ctx, value, int(right - ext.width), y, color, size)


def text_width(ctx: cairo.Context, value: str, size: int = 10) -> int:
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    return int(ctx.text_extents(value).width)


def accel_text(
    ctx: cairo.Context,
    value: str,
    x: int,
    y: int,
    accel: str | None = None,
    size: int = 8,
    color: tuple[float, float, float] = INK_BLACK,
) -> None:
    if not accel:
        text(ctx, value, x, y, color, size)
        return
    index = value.lower().find(accel.lower())
    if index < 0:
        text(ctx, value, x, y, color, size)
        return
    before = value[:index]
    hot = value[index:index + 1]
    after = value[index + 1:]
    cursor = x
    if before:
        text(ctx, before, cursor, y, color, size)
        cursor += text_width(ctx, before, size)
    text(ctx, hot, cursor, y, ACCENT_ORANGE, size, cairo.FONT_WEIGHT_BOLD)
    cursor += text_width(ctx, hot, size)
    if after:
        text(ctx, after, cursor, y, color, size)


def fit_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 2:
        return value[:limit]
    return value[: limit - 2] + ".."


def compact_path(path: Path) -> str:
    return str(path)


def size_label(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "-"
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.1f} {unit}"


def date_label(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return "-- -- --:--"
    return datetime.fromtimestamp(stamp).strftime("%b %d %H:%M")


def icon_for(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    kind, _ = mimetypes.guess_type(path.name)
    if kind:
        if kind.startswith("image/"):
            return "image"
        if kind.startswith("text/"):
            return "text"
    suffix = path.suffix.lower()
    if suffix in {".zip", ".gz", ".xz", ".tar", ".tgz", ".7z", ".rar"}:
        return "zip"
    return "text"


def list_items(path: Path) -> list[FileItem]:
    items = [
        FileItem(".", path, "folder", "-", date_label(path), True, is_current=True),
        FileItem("..", path.parent if path.parent != path else path, "folder", "-", date_label(path.parent), True, is_parent=True),
    ]
    for child in file_backend.list_dir(path)[:96]:
        is_dir = child.is_dir()
        items.append(FileItem(child.name, child, icon_for(child, is_dir), size_label(child, is_dir), date_label(child), is_dir))
    return items


def draw_folder_icon(ctx: cairo.Context, x: int, y: int) -> None:
    ctx.set_line_width(1)
    set_color(ctx, INK_BLACK)
    ctx.move_to(x + 1, y + 5)
    ctx.line_to(x + 6, y + 5)
    ctx.line_to(x + 8, y + 7)
    ctx.line_to(x + 15, y + 7)
    ctx.line_to(x + 15, y + 15)
    ctx.line_to(x + 1, y + 15)
    ctx.close_path()
    ctx.stroke()


def draw_file_icon(ctx: cairo.Context, x: int, y: int) -> None:
    stroke_rect(ctx, x + 3, y + 1, 11, 16, INK_BLACK)
    line(ctx, x + 6, y + 5, x + 11, y + 5, INK_BLACK)
    line(ctx, x + 6, y + 9, x + 11, y + 9, INK_BLACK)
    line(ctx, x + 6, y + 13, x + 11, y + 13, INK_BLACK)


def draw_image_icon(ctx: cairo.Context, x: int, y: int) -> None:
    stroke_rect(ctx, x + 2, y + 2, 13, 14, INK_BLACK)
    ctx.arc(x + 6, y + 6, 1, 0, math.tau)
    ctx.stroke()
    ctx.move_to(x + 3, y + 14)
    ctx.line_to(x + 7, y + 10)
    ctx.line_to(x + 10, y + 13)
    ctx.line_to(x + 12, y + 10)
    ctx.line_to(x + 15, y + 14)
    ctx.stroke()


def draw_zip_icon(ctx: cairo.Context, x: int, y: int) -> None:
    stroke_rect(ctx, x + 3, y + 1, 11, 16, INK_BLACK)
    for yy in (3, 6, 9, 12):
        line(ctx, x + 8, y + yy, x + 8, y + yy + 1, INK_BLACK)
        line(ctx, x + 9, y + yy + 1, x + 9, y + yy + 2, INK_BLACK)
    ctx.arc(x + 8.5, y + 15, 1, 0, math.tau)
    ctx.stroke()


def draw_icon(ctx: cairo.Context, name: str, x: int, y: int) -> None:
    if name == "folder":
        draw_folder_icon(ctx, x, y)
    elif name == "image":
        draw_image_icon(ctx, x, y)
    elif name == "zip":
        draw_zip_icon(ctx, x, y)
    else:
        draw_file_icon(ctx, x, y)


def draw_keycap(ctx: cairo.Context, x: int, y: int, label: str, w: int = 28,
                accent: bool = False, accel: str | None = None) -> None:
    top_h = 10
    front_h = 3
    fill_rect(ctx, x + 1, y + top_h + 1, w, front_h, HARD_SHADOW)
    fill_rect(ctx, x, y, w, top_h + 1, ICON_WELL if not accent else SELECT_FILL)

    outline = ACCENT_ORANGE if accent else LINE_BLACK
    set_color(ctx, outline)
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

    line(ctx, x + 2, y + top_h, x + w - 3, y + top_h, LINE_BLACK)
    line(ctx, x + 3, y + top_h + 2, x + w - 5, y + top_h + 2, LINE_BLACK)
    line(ctx, x + w - 3, y + top_h + 1, x + w - 1, y + top_h - 1, LINE_BLACK)
    if accel:
        accel_text(ctx, label, x + 4, y + 9, accel, 8)
    else:
        text(ctx, label, x + 4, y + 9, INK_BLACK, 8)


def draw_section_title(ctx: cairo.Context, x: int, y: int, w: int, title: str) -> None:
    fill_rect(ctx, x + 1, y + 1, w - 2, 17, TITLE_FILL)
    line(ctx, x, y + 18, x + w - 1, y + 18)
    text(ctx, title, x + 8, y + 13, ACCENT_ORANGE, 9, cairo.FONT_WEIGHT_BOLD)


def draw_shortcuts(ctx: cairo.Context, menu_open: bool) -> None:
    panel(ctx, LEFT_X, PANEL_Y, LEFT_W, PANEL_H)
    draw_section_title(ctx, LEFT_X, PANEL_Y, LEFT_W, "KEYS")

    rows = [
        ("UP", "U", 56),
        ("DOWN", "D", 56),
        ("OPEN", "O", 56),
        ("BACK", "B", 56),
        ("MENU", "M", 56),
        ("REFRESH", "R", 56),
        ("TRASH", "T", 56),
    ]
    for index, (key, accel, key_w) in enumerate(rows):
        y = PANEL_Y + 25 + index * 16
        draw_keycap(ctx, LEFT_X + 7, y, key, key_w, menu_open and key == "Menu", accel)


def draw_files(ctx: cairo.Context, rows: list[FileItem], selected: int, scroll: int) -> None:
    x, y, w, h = RIGHT_X, PANEL_Y, RIGHT_W, PANEL_H
    panel(ctx, x, y, w, h)

    header_h = 16
    fill_rect(ctx, x + 1, y + 1, w - 2, header_h, TITLE_FILL)
    text(ctx, "NAME", x + 26, y + 12, ACCENT_ORANGE, 8, cairo.FONT_WEIGHT_BOLD)
    text(ctx, "SIZE", x + 137, y + 12, ACCENT_ORANGE, 8, cairo.FONT_WEIGHT_BOLD)
    text_right(ctx, "MODIFIED", x + w - 8, y + 12, ACCENT_ORANGE, 8)
    line(ctx, x, y + header_h, x + w - 1, y + header_h)

    list_y = y + header_h + 1
    row_h = 17
    visible_rows = rows[scroll:scroll + VISIBLE_ROWS]
    for visual_index, row in enumerate(visible_rows):
        actual_index = scroll + visual_index
        row_y = list_y + visual_index * row_h
        if actual_index == selected:
            fill_rect(ctx, x + 1, row_y + 1, w - 2, row_h - 1, SELECT_FILL)
            stroke_rect(ctx, x + 1, row_y + 1, w - 2, row_h, ACCENT_ORANGE)
        elif visual_index < len(visible_rows) - 1:
            line(ctx, x + 1, row_y + row_h, x + w - 2, row_y + row_h, HARD_SHADOW)

        draw_icon(ctx, row.icon, x + 7, row_y)
        name_color = ACCENT_ORANGE if row.is_parent else INK_BLACK
        text(ctx, fit_text(row.name, 15), x + 29, row_y + 12, name_color, 9)
        text(ctx, row.size, x + 137, row_y + 12, MUTED_TEXT, 8)
        text_right(ctx, row.date, x + w - 8, row_y + 12, MUTED_TEXT, 8)

    if not visible_rows:
        text(ctx, "EMPTY", x + 91, y + 78, MUTED_TEXT, 10)


def draw_bottom_bar(ctx: cairo.Context, state: "FilesState") -> None:
    fill_rect(ctx, 0, MAIN_H, WIDTH, BOTTOM_H, ZERO_PAPER)
    line(ctx, 0, MAIN_H, WIDTH, MAIN_H)
    status = state.error or state.status_text()
    status_color = WARN_RED if state.error else MUTED_TEXT
    text(ctx, "PATH", 6, 164, ACCENT_ORANGE, 8, cairo.FONT_WEIGHT_BOLD)
    text(ctx, fit_text(compact_path(state.current_path), 31), 33, 164, INK_BLACK, 8)
    text_right(ctx, fit_text(status.upper(), 15), WIDTH - 6, 164, status_color, 8)


def draw_menu(ctx: cairo.Context, state: "FilesState") -> None:
    x, y, w, h = 158, 18, 156, 125
    panel(ctx, x, y, w, h)
    draw_section_title(ctx, x, y, w, "ACTIONS")
    draw_keycap(ctx, x + w - 46, y + 3, "MENU", 38, False, "M")

    row_h = 14
    visible = state.menu_visible_actions()
    for visual_index, action in enumerate(visible):
        actual_index = state.menu_scroll + visual_index
        row_y = y + 21 + visual_index * row_h
        selected = actual_index == state.menu_selected
        enabled = state.menu_action_enabled(action.action_id)
        if selected:
            fill_rect(ctx, x + 4, row_y, w - 8, row_h - 1, SELECT_FILL)
            stroke_rect(ctx, x + 4, row_y, w - 8, row_h, ACCENT_ORANGE)
        draw_keycap(ctx, x + 9, row_y + 1, action.label, w - 20, selected and enabled, action.key)

    if state.menu_scroll > 0:
        text(ctx, "^", x + w - 11, y + 27, MUTED_TEXT, 8)
    if state.menu_scroll + state.menu_visible_count < len(MENU_ACTIONS):
        text(ctx, "v", x + w - 11, y + h - 8, MUTED_TEXT, 8)


def draw_info(ctx: cairo.Context, state: "FilesState") -> None:
    x, y, w, h = 86, 31, 226, 89
    panel(ctx, x, y, w, h)
    draw_section_title(ctx, x, y, w, "PROPERTIES")
    draw_keycap(ctx, x + w - 51, y + 3, "CLOSE", 44, False, "C")
    for index, row in enumerate(state.info_lines[:5]):
        label, value = row
        row_y = y + 32 + index * 11
        text(ctx, label, x + 9, row_y, MUTED_TEXT, 8)
        text(ctx, fit_text(value, 26), x + 56, row_y, INK_BLACK, 8)


def draw_files_page(ctx: cairo.Context, state: "FilesState | None" = None) -> None:
    configure_crisp(ctx)
    if state is None:
        state = FilesState()
    fill_rect(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
    draw_shortcuts(ctx, state.menu_open)
    draw_files(ctx, state.rows, state.selected_row, state.scroll)
    draw_bottom_bar(ctx, state)
    if state.menu_open:
        draw_menu(ctx, state)
    if state.info_open:
        draw_info(ctx, state)


class FilesState:
    def __init__(self) -> None:
        self.current_path = Path.home()
        self.selected_row = 0
        self.scroll = 0
        self.rows: list[FileItem] = []
        self.status = "Ready"
        self.error = ""
        self.menu_open = False
        self.menu_selected = 0
        self.menu_scroll = 0
        self.menu_visible_count = 7
        self.info_open = False
        self.info_lines: list[tuple[str, str]] = []
        self.reload("Ready")

    def status_text(self) -> str:
        count = max(0, len(self.rows) - 2)
        if self.status and self.status != "Ready":
            return self.status
        return f"{count} item" + ("" if count == 1 else "s")

    def set_status(self, value: str) -> None:
        self.status = value
        self.error = ""

    def set_error(self, value: str) -> None:
        self.error = value or "Error"

    def reload(self, status: str | None = None) -> None:
        self.menu_open = False
        self.info_open = False
        if not self.current_path.exists():
            self.set_error(f"Missing: {self.current_path.name}")
            self.rows = [
                FileItem(".", self.current_path, "folder", "-", "-- -- --:--", True, is_current=True),
                FileItem("..", self.current_path.parent, "folder", "-", "-- -- --:--", True, is_parent=True),
            ]
        elif not self.current_path.is_dir():
            self.set_error("Not a directory")
            self.current_path = self.current_path.parent
            self.rows = list_items(self.current_path)
        else:
            self.rows = list_items(self.current_path)
            if status is not None:
                self.set_status(status)
            elif self.error:
                self.error = ""
        self.selected_row = min(self.selected_row, max(0, len(self.rows) - 1))
        self.keep_visible()

    def keep_visible(self) -> None:
        if self.selected_row < self.scroll:
            self.scroll = self.selected_row
        if self.selected_row >= self.scroll + VISIBLE_ROWS:
            self.scroll = self.selected_row - (VISIBLE_ROWS - 1)
        self.scroll = max(0, min(self.scroll, max(0, len(self.rows) - VISIBLE_ROWS)))

    def selected_item(self) -> FileItem | None:
        if not self.rows:
            return None
        return self.rows[self.selected_row]

    def move(self, delta: int) -> None:
        if not self.rows:
            return
        self.selected_row = (self.selected_row + delta) % len(self.rows)
        self.keep_visible()
        self.error = ""

    def open_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        if item.is_dir:
            self.current_path = item.path
            self.selected_row = 0
            self.scroll = 0
            self.reload("Opened")
            return
        result = file_backend.open_path(item.path)
        if result.ok:
            self.set_status("Opening")
        else:
            self.set_error(result.text or "Open failed")

    def go_parent(self) -> None:
        parent = self.current_path.parent
        if parent != self.current_path:
            self.current_path = parent
            self.selected_row = 0
            self.scroll = 0
            self.reload("Parent")
        else:
            self.set_status("At root")

    def go_home(self) -> None:
        self.current_path = Path.home()
        self.selected_row = 0
        self.scroll = 0
        self.reload("Home")

    def refresh(self) -> None:
        self.reload("Refreshed")

    def create_folder(self) -> None:
        if not self.current_path.is_dir():
            self.set_error("Not a directory")
            return
        for index in range(1, 100):
            name = "New Folder" if index == 1 else f"New Folder {index}"
            candidate = self.current_path / name
            if candidate.exists():
                continue
            try:
                candidate.mkdir()
            except OSError as exc:
                self.set_error(str(exc))
                return
            self.reload("Folder created")
            self.select_path(candidate)
            return
        self.set_error("Name unavailable")

    def trash_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        if item.is_current or item.is_parent:
            self.set_error("Cannot trash this")
            return
        result = file_backend.trash_path(item.path)
        if result.ok:
            self.reload("Moved to trash")
        else:
            self.set_error(result.text or "Trash failed")

    def show_properties(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        kind = "Folder" if item.is_dir else "File"
        try:
            modified = datetime.fromtimestamp(item.path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            modified = "Unknown"
        self.info_lines = [
            ("Name", item.name),
            ("Type", kind),
            ("Size", item.size),
            ("Modified", modified),
            ("Path", compact_path(item.path)),
        ]
        self.info_open = True
        self.menu_open = False
        self.error = ""

    def select_path(self, path: Path) -> None:
        for index, row in enumerate(self.rows):
            if row.path == path and row.name == path.name:
                self.selected_row = index
                self.keep_visible()
                return

    def open_menu(self) -> None:
        self.menu_open = True
        self.info_open = False
        self.error = ""
        self.keep_menu_visible()

    def close_menu(self) -> None:
        self.menu_open = False

    def move_menu(self, delta: int) -> None:
        self.menu_selected = (self.menu_selected + delta) % len(MENU_ACTIONS)
        self.keep_menu_visible()

    def keep_menu_visible(self) -> None:
        if self.menu_selected < self.menu_scroll:
            self.menu_scroll = self.menu_selected
        if self.menu_selected >= self.menu_scroll + self.menu_visible_count:
            self.menu_scroll = self.menu_selected - (self.menu_visible_count - 1)
        self.menu_scroll = max(0, min(self.menu_scroll, max(0, len(MENU_ACTIONS) - self.menu_visible_count)))

    def menu_visible_actions(self) -> list[MenuAction]:
        return MENU_ACTIONS[self.menu_scroll:self.menu_scroll + self.menu_visible_count]

    def menu_action_enabled(self, action_id: str) -> bool:
        item = self.selected_item()
        if action_id in {"trash", "properties", "open"} and item is None:
            return False
        if action_id == "trash" and item is not None and (item.is_current or item.is_parent):
            return False
        return True

    def run_menu_action(self) -> None:
        action = MENU_ACTIONS[self.menu_selected]
        self.run_action(action.action_id)

    def run_action(self, action_id: str) -> None:
        self.menu_open = False
        if not self.menu_action_enabled(action_id):
            self.set_error("Unavailable")
            return
        if action_id == "open":
            self.open_selected()
        elif action_id == "parent":
            self.go_parent()
        elif action_id == "home":
            self.go_home()
        elif action_id == "new_folder":
            self.create_folder()
        elif action_id == "trash":
            self.trash_selected()
        elif action_id == "properties":
            self.show_properties()
        elif action_id == "refresh":
            self.refresh()


class FilesCanvas(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.state = FilesState()
        self.set_content_width(WIDTH)
        self.set_content_height(HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_draw_func(self._draw)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        self.set_focusable(True)

    def _draw(self, _area: Gtk.DrawingArea, ctx: cairo.Context, _width: int, _height: int) -> None:
        draw_files_page(ctx, self.state)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        handled = self.handle_key(keyval)
        if handled:
            self.queue_draw()
        return handled

    def handle_key(self, keyval: int) -> bool:
        if self.state.info_open:
            if keyval in (Gdk.KEY_c, Gdk.KEY_C):
                self.state.info_open = False
                return True
            return False

        if self.state.menu_open:
            if keyval in (Gdk.KEY_m, Gdk.KEY_M):
                self.state.close_menu()
            elif keyval in (Gdk.KEY_Down, Gdk.KEY_Right):
                self.state.move_menu(1)
            elif keyval in (Gdk.KEY_Up, Gdk.KEY_Left):
                self.state.move_menu(-1)
            elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.state.run_menu_action()
            elif keyval in (Gdk.KEY_h, Gdk.KEY_H):
                self.state.run_action("home")
            elif keyval in (Gdk.KEY_n, Gdk.KEY_N):
                self.state.run_action("new_folder")
            elif keyval in (Gdk.KEY_p, Gdk.KEY_P):
                self.state.run_action("properties")
            else:
                return False
            return True

        if keyval in (Gdk.KEY_Down, Gdk.KEY_d, Gdk.KEY_D):
            self.state.move(1)
        elif keyval in (Gdk.KEY_Up, Gdk.KEY_u, Gdk.KEY_U):
            self.state.move(-1)
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_o, Gdk.KEY_O):
            self.state.open_selected()
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_BackSpace, Gdk.KEY_b, Gdk.KEY_B):
            self.state.go_parent()
        elif keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self.state.open_menu()
        elif keyval in (Gdk.KEY_r, Gdk.KEY_R):
            self.state.refresh()
        elif keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.state.go_home()
        elif keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self.state.show_properties()
        elif keyval in (Gdk.KEY_Delete, Gdk.KEY_t, Gdk.KEY_T):
            self.state.trash_selected()
        else:
            return False
        return True
