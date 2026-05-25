from __future__ import annotations

import time

import cairo

from czero_apps.apps.settings.backend import SettingsBackend
from czero_apps.apps.settings.model import Category, SelectorOption, SettingRow, StackPage
from czero_apps.ui.gtk import Gdk, GLib, Gtk
from czero_apps.ui.theme import load_css


WIDTH = 320
HEIGHT = 170
MAIN_H = 150
BOTTOM_H = 20

SIDEBAR_X = 4
SIDEBAR_Y = 4
SIDEBAR_W = 76
SIDEBAR_H = 142
DETAIL_X = 84
DETAIL_Y = 4
DETAIL_W = 232
DETAIL_H = 142

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


CATEGORIES = (
    Category("system", "System", "gear"),
    Category("display", "Display", "display"),
    Category("network", "Network", "network"),
    Category("sound", "Sound", "sound"),
    Category("power", "Power", "power"),
    Category("about", "About", "info"),
)


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
    size: int = 8,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> None:
    set_color(ctx, color)
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    ctx.move_to(x, y)
    ctx.show_text(value)


def text_width(ctx: cairo.Context, value: str, size: int = 8, weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL) -> int:
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    return int(ctx.text_extents(value).width)


def text_right(
    ctx: cairo.Context,
    value: str,
    right: int,
    y: int,
    color: tuple[float, float, float] = INK_BLACK,
    size: int = 8,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> None:
    text(ctx, value, right - text_width(ctx, value, size, weight), y, color, size, weight)


def fit_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 2:
        return value[:limit]
    return value[: limit - 2] + ".."


def fit_text_px(
    ctx: cairo.Context,
    value: str,
    max_width: int,
    size: int = 8,
    weight: cairo.FontWeight = cairo.FONT_WEIGHT_NORMAL,
) -> str:
    if text_width(ctx, value, size, weight) <= max_width:
        return value
    if max_width <= text_width(ctx, "..", size, weight):
        return ""
    lo = 0
    hi = len(value)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(ctx, value[:mid] + "..", size, weight) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return value[:lo] + ".."


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
    text(ctx, label, x + 5, y + 10, INK_BLACK, 8)


def draw_icon(ctx: cairo.Context, icon: str, x: int, y: int, color: tuple[float, float, float] = INK_BLACK) -> None:
    ctx.new_path()
    set_color(ctx, color)
    ctx.set_line_width(1)
    if icon == "gear":
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 6, 0, 6.283)
        ctx.stroke()
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 2, 0, 6.283)
        ctx.stroke()
        for dx, dy in ((8, 0), (8, 16), (0, 8), (16, 8)):
            line(ctx, x + 8, y + 8, x + dx, y + dy, color)
    elif icon == "display":
        stroke_rect(ctx, x + 2, y + 3, 13, 9, color)
        line(ctx, x + 8, y + 12, x + 8, y + 16, color)
        line(ctx, x + 4, y + 16, x + 13, y + 16, color)
    elif icon == "network":
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 7, 0, 6.283)
        ctx.stroke()
        line(ctx, x + 1, y + 8, x + 15, y + 8, color)
        line(ctx, x + 8, y + 1, x + 8, y + 15, color)
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 4, -1.57, 1.57)
        ctx.stroke()
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 4, 1.57, 4.71)
        ctx.stroke()
    elif icon == "sound":
        ctx.new_path()
        ctx.move_to(x + 2, y + 6)
        ctx.line_to(x + 6, y + 6)
        ctx.line_to(x + 11, y + 2)
        ctx.line_to(x + 11, y + 14)
        ctx.line_to(x + 6, y + 10)
        ctx.line_to(x + 2, y + 10)
        ctx.close_path()
        ctx.stroke()
        ctx.new_path()
        ctx.arc(x + 12, y + 8, 4, -0.8, 0.8)
        ctx.stroke()
    elif icon == "power":
        stroke_rect(ctx, x + 2, y + 5, 12, 7, color)
        stroke_rect(ctx, x + 14, y + 7, 2, 3, color)
        fill_rect(ctx, x + 4, y + 7, 4, 3, color)
    elif icon == "info":
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 7, 0, 6.283)
        ctx.stroke()
        text(ctx, "i", x + 6, y + 12, color, 11, cairo.FONT_WEIGHT_BOLD)
    else:
        ctx.new_path()
        ctx.arc(x + 8, y + 8, 2, 0, 6.283)
        ctx.stroke()
    ctx.new_path()


class SettingsCanvas(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.backend = SettingsBackend()
        self.category_index = 1
        self.selected_row = 0
        self.focus_area = "sidebar"
        self.stack: list[StackPage] = []
        self.error_text = ""
        self.error_until = 0.0
        self.set_content_width(WIDTH)
        self.set_content_height(HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_focusable(True)
        self.set_draw_func(self._draw)
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        GLib.timeout_add_seconds(2, self.refresh)

    def current_category(self) -> Category:
        return CATEGORIES[self.category_index]

    def current_rows(self) -> tuple[SettingRow, ...]:
        if self.stack:
            return self.stack[-1].rows
        return self.backend.page(self.current_category().id).rows

    def current_count(self) -> int:
        if self.focus_area == "sidebar" and not self.stack:
            return len(CATEGORIES)
        if self.stack:
            page = self.stack[-1]
            if page.options:
                return len(page.options)
            if page.rows:
                return len(page.rows)
            return 1
        return len(self.current_rows())

    def refresh(self) -> bool:
        self.queue_draw()
        return True

    def show_feedback(self, text_value: str, is_error: bool = False) -> None:
        self.error_text = text_value
        self.error_until = time.monotonic() + (3.0 if is_error else 1.8)
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, ctx: cairo.Context, _width: int, _height: int) -> None:
        configure_crisp(ctx)
        fill_rect(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
        self.draw_sidebar(ctx)
        self.draw_detail(ctx)
        self.draw_bottom_bar(ctx)

    def draw_sidebar(self, ctx: cairo.Context) -> None:
        panel(ctx, SIDEBAR_X, SIDEBAR_Y, SIDEBAR_W, SIDEBAR_H)
        row_h = 22
        for index, category in enumerate(CATEGORIES):
            y = SIDEBAR_Y + 5 + index * row_h
            current = index == self.category_index and not self.stack
            focused = current and self.focus_area == "sidebar"
            if current:
                fill_rect(ctx, SIDEBAR_X + 4, y - 2, SIDEBAR_W - 8, 19, SELECT_FILL)
                stroke_rect(ctx, SIDEBAR_X + 4, y - 2, SIDEBAR_W - 8, 19, ACCENT_ORANGE if focused else LINE_BLACK)
            color = ACCENT_ORANGE if current else INK_BLACK
            draw_icon(ctx, category.icon, SIDEBAR_X + 8, y, INK_BLACK)
            text(ctx, fit_text(category.label, 7), SIDEBAR_X + 29, y + 12, color, 9, cairo.FONT_WEIGHT_BOLD if focused else cairo.FONT_WEIGHT_NORMAL)

    def draw_detail(self, ctx: cairo.Context) -> None:
        panel(ctx, DETAIL_X, DETAIL_Y, DETAIL_W, DETAIL_H)
        if self.stack:
            self.draw_stack_page(ctx, self.stack[-1])
        else:
            page = self.backend.page(self.current_category().id)
            rows = page.rows
            offset = self.visible_offset(len(rows), 6)
            for local_index, row in enumerate(rows[offset : offset + 6]):
                row_index = offset + local_index
                self.draw_row(ctx, row, local_index, self.focus_area == "detail" and row_index == self.selected_row)
            if len(rows) > 6:
                self.draw_scroll_hint(ctx, len(rows), offset, 6)
        if self.error_text and time.monotonic() < self.error_until:
            self.draw_error(ctx, self.error_text)

    def draw_row(self, ctx: cairo.Context, row: SettingRow, index: int, selected: bool) -> None:
        x = DETAIL_X + 8
        y = DETAIL_Y + 8 + index * 22
        w = DETAIL_W - 16
        h = 20
        if selected:
            fill_rect(ctx, x - 3, y - 2, w + 6, h, SELECT_FILL)
            stroke_rect(ctx, x - 3, y - 2, w + 6, h, ACCENT_ORANGE)
        color = MUTED_TEXT if row.disabled else INK_BLACK
        text(ctx, fit_text(row.label, 15), x, y + 12, color, 9, cairo.FONT_WEIGHT_BOLD if selected else cairo.FONT_WEIGHT_NORMAL)
        if row.kind == "slider":
            text_right(ctx, row.value, x + 154, y + 12, MUTED_TEXT if not selected else ACCENT_ORANGE, 9)
            self.draw_slider(ctx, x + 163, y + 5, 44, row.slider_value, row.disabled)
        elif row.kind == "toggle":
            text_right(ctx, row.value, x + 151, y + 12, MUTED_TEXT, 9)
            self.draw_toggle(ctx, x + 166, y + 3, row.toggle_on, row.disabled)
        else:
            leader_start = x + min(104, text_width(ctx, row.label, 9) + 8)
            value_right = x + (194 if row.arrow else 206)
            value_left = x + 118
            leader_end = max(leader_start, value_left - 7)
            for dot_x in range(leader_start, leader_end, 6):
                fill_rect(ctx, dot_x, y + 9, 1, 1, MUTED_TEXT)
            value_color = MUTED_TEXT if row.disabled else (ACCENT_ORANGE if selected else INK_BLACK)
            value = fit_text_px(ctx, row.value, value_right - value_left, 9)
            text_right(ctx, value, value_right, y + 12, value_color, 9)
            if row.arrow:
                text(ctx, ">", x + 201, y + 12, INK_BLACK, 9, cairo.FONT_WEIGHT_BOLD)

    def draw_slider(self, ctx: cairo.Context, x: int, y: int, w: int, value: int, disabled: bool) -> None:
        color = MUTED_TEXT if disabled else LINE_BLACK
        line(ctx, x, y + 5, x + w, y + 5, color)
        knob_x = x + round(w * max(0, min(100, value)) / 100)
        fill_rect(ctx, knob_x - 3, y + 2, 7, 7, ICON_WELL if not disabled else PANEL_CREAM)
        stroke_rect(ctx, knob_x - 3, y + 2, 7, 7, color)

    def draw_toggle(self, ctx: cairo.Context, x: int, y: int, on: bool, disabled: bool) -> None:
        fill_rect(ctx, x, y, 29, 12, ICON_WELL if not disabled else PANEL_CREAM)
        stroke_rect(ctx, x, y, 29, 12, MUTED_TEXT if disabled else LINE_BLACK)
        if on:
            fill_rect(ctx, x + 2, y + 2, 15, 8, ACCENT_ORANGE if not disabled else MUTED_TEXT)
            fill_rect(ctx, x + 18, y + 2, 8, 8, ICON_WELL)
            stroke_rect(ctx, x + 18, y + 2, 8, 8, LINE_BLACK)
        else:
            fill_rect(ctx, x + 3, y + 2, 8, 8, ICON_WELL)
            stroke_rect(ctx, x + 3, y + 2, 8, 8, LINE_BLACK)

    def draw_stack_page(self, ctx: cairo.Context, page: StackPage) -> None:
        text(ctx, page.title, DETAIL_X + 9, DETAIL_Y + 14, ACCENT_ORANGE, 10, cairo.FONT_WEIGHT_BOLD)
        line(ctx, DETAIL_X + 1, DETAIL_Y + 20, DETAIL_X + DETAIL_W - 2, DETAIL_Y + 20)
        if page.message:
            text(ctx, fit_text(page.message, 27), DETAIL_X + 10, DETAIL_Y + 46, INK_BLACK, 10)
            text(ctx, "Enter Confirm", DETAIL_X + 10, DETAIL_Y + 76, MUTED_TEXT, 9)
            text(ctx, "Cancel Back", DETAIL_X + 10, DETAIL_Y + 96, MUTED_TEXT, 9)
            return
        if page.kind in {"text", "password"}:
            label = "Password" if page.kind == "password" else "Value"
            shown = "*" * len(page.text_value) if page.kind == "password" else page.text_value
            text(ctx, label, DETAIL_X + 12, DETAIL_Y + 44, INK_BLACK, 9, cairo.FONT_WEIGHT_BOLD)
            fill_rect(ctx, DETAIL_X + 12, DETAIL_Y + 55, DETAIL_W - 24, 22, ICON_WELL)
            stroke_rect(ctx, DETAIL_X + 12, DETAIL_Y + 55, DETAIL_W - 24, 22, ACCENT_ORANGE)
            text(ctx, fit_text_px(ctx, shown, DETAIL_W - 36, 10), DETAIL_X + 18, DETAIL_Y + 70, INK_BLACK, 10)
            text(ctx, "Enter Apply", DETAIL_X + 12, DETAIL_Y + 103, MUTED_TEXT, 9)
            text(ctx, "Cancel Back", DETAIL_X + 12, DETAIL_Y + 122, MUTED_TEXT, 9)
            return
        if page.rows:
            offset = self.visible_offset(len(page.rows), 5)
            for local_index, row in enumerate(page.rows[offset : offset + 5]):
                row_index = offset + local_index
                self.draw_stack_row(ctx, row, local_index, row_index == self.selected_row)
            if len(page.rows) > 5:
                self.draw_scroll_hint(ctx, len(page.rows), offset, 5)
            return
        options = page.options
        offset = self.visible_offset(len(options), 5)
        for local_index, option in enumerate(options[offset : offset + 5]):
            index = offset + local_index
            y = DETAIL_Y + 30 + local_index * 21
            selected = index == self.selected_row
            if selected:
                fill_rect(ctx, DETAIL_X + 8, y - 12, DETAIL_W - 16, 18, SELECT_FILL)
                stroke_rect(ctx, DETAIL_X + 8, y - 12, DETAIL_W - 16, 18, ACCENT_ORANGE)
            mark = "*" if option.selected else " "
            text(ctx, mark, DETAIL_X + 14, y, ACCENT_ORANGE if option.selected else MUTED_TEXT, 9)
            text(ctx, fit_text_px(ctx, option.label, DETAIL_W - 48, 9), DETAIL_X + 28, y, INK_BLACK, 9)
        if len(options) > 5:
            self.draw_scroll_hint(ctx, len(options), offset, 5)

    def visible_offset(self, total: int, visible: int) -> int:
        if total <= visible:
            return 0
        return max(0, min(self.selected_row - visible + 1, total - visible))

    def draw_scroll_hint(self, ctx: cairo.Context, total: int, offset: int, visible: int) -> None:
        x = DETAIL_X + DETAIL_W - 7
        y = DETAIL_Y + 25
        h = DETAIL_H - 36
        line(ctx, x, y, x, y + h, HARD_SHADOW)
        knob_h = max(9, int(h * visible / total))
        knob_y = y + int((h - knob_h) * offset / max(1, total - visible))
        fill_rect(ctx, x - 2, knob_y, 5, knob_h, ACCENT_ORANGE)

    def draw_stack_row(self, ctx: cairo.Context, row: SettingRow, index: int, selected: bool) -> None:
        x = DETAIL_X + 12
        y = DETAIL_Y + 32 + index * 20
        if selected:
            fill_rect(ctx, x - 4, y - 13, DETAIL_W - 16, 18, SELECT_FILL)
            stroke_rect(ctx, x - 4, y - 13, DETAIL_W - 16, 18, ACCENT_ORANGE)
        text(ctx, fit_text_px(ctx, row.label, 76, 9, cairo.FONT_WEIGHT_BOLD if selected else cairo.FONT_WEIGHT_NORMAL), x, y, INK_BLACK, 9, cairo.FONT_WEIGHT_BOLD if selected else cairo.FONT_WEIGHT_NORMAL)
        text_right(ctx, fit_text_px(ctx, row.value, 122, 9), DETAIL_X + DETAIL_W - 14, y, MUTED_TEXT if not selected else ACCENT_ORANGE, 9)

    def draw_error(self, ctx: cairo.Context, message: str) -> None:
        x = DETAIL_X + 7
        y = DETAIL_Y + DETAIL_H - 22
        fill_rect(ctx, x, y, DETAIL_W - 14, 17, SELECT_FILL)
        stroke_rect(ctx, x, y, DETAIL_W - 14, 17, WARN_RED)
        text(ctx, fit_text(message, 28), x + 5, y + 12, WARN_RED, 8, cairo.FONT_WEIGHT_BOLD)

    def draw_bottom_bar(self, ctx: cairo.Context) -> None:
        y = MAIN_H
        fill_rect(ctx, 0, y, WIDTH, BOTTOM_H, ZERO_PAPER)
        line(ctx, 0, y, WIDTH, y)
        keycap(ctx, 5, y + 3, "UP", 25)
        keycap(ctx, 33, y + 3, "DN", 25)
        text(ctx, "Select", 64, y + 13, INK_BLACK, 8)
        keycap(ctx, 111, y + 3, "C", 19)
        text(ctx, "Cat", 136, y + 13, INK_BLACK, 8)
        keycap(ctx, 166, y + 3, "ENT", 31)
        text(ctx, "Enter", 202, y + 13, INK_BLACK, 8)
        keycap(ctx, 252, y + 3, "B", 19)
        text(ctx, "Back", 277, y + 13, INK_BLACK, 8)

    def push_selector(self, row: SettingRow) -> None:
        if row.key == "hostname":
            self.stack.append(StackPage("Hostname", kind="text", field_key="hostname", text_value=row.value))
            self.selected_row = 0
            return
        if row.key == "connection":
            networks = self.backend.wifi_networks()
            if not networks:
                self.show_feedback("No Wi-Fi networks", True)
                return
            self.stack.append(StackPage(
                "Wi-Fi",
                kind="wifi",
                options=tuple(SelectorOption(f"{ssid} {signal}% {'lock' if locked else ''}", ssid) for ssid, signal, locked in networks),
            ))
            self.selected_row = 0
            return
        if row.key == "advanced":
            self.stack.append(StackPage("Network Detail", kind="rows", rows=self.backend.network_advanced_rows()))
            self.selected_row = 0
            return
        if row.key in {"output", "input"}:
            devices = self.backend.audio_sinks() if row.key == "output" else self.backend.audio_sources()
            self.stack.append(StackPage(
                row.label,
                kind=f"audio-{row.key}",
                options=tuple(SelectorOption(fit_text(label, 24), value) for value, label in devices),
            ))
            self.selected_row = 0
            return
        options = self.backend.selector_options(row.key)
        if not options:
            self.show_feedback("No selector yet", True)
            return
        current = row.value.lower().replace(" ", "").replace("sec", "s")
        stack_options = tuple(
            SelectorOption(
                label=value.replace("-", " ").title() if value in {"manual", "on-startup"} else value,
                value=value,
                selected=value.lower().replace(" ", "") == current,
            )
            for value in options
        )
        self.stack.append(StackPage(row.label, kind="selector", options=stack_options))
        self.selected_row = 0

    def activate_row(self) -> None:
        if self.stack:
            page = self.stack[-1]
            if page.confirm_action:
                feedback = self.backend.action(page.confirm_action)
                self.stack.pop()
                self.show_feedback(feedback.text, not feedback.ok)
                return
            if page.kind == "text":
                feedback = self.backend.set_hostname(page.text_value)
                self.stack.pop()
                self.selected_row = 0
                self.show_feedback(feedback.text, not feedback.ok)
                return
            if page.kind == "password":
                feedback = self.backend.connect_wifi(page.password_target, page.text_value)
                self.stack.pop()
                self.selected_row = 0
                self.show_feedback(feedback.text, not feedback.ok)
                return
            if page.options:
                if self.selected_row >= len(page.options):
                    self.selected_row = 0
                option = page.options[self.selected_row]
                if page.kind == "wifi":
                    self.stack.append(StackPage(fit_text(option.value, 16), kind="password", text_value="", password_target=option.value))
                    self.selected_row = 0
                    return
                if page.kind in {"audio-output", "audio-input"}:
                    feedback = self.backend.set_audio_device("output" if page.kind == "audio-output" else "input", option.value)
                    self.stack.pop()
                    self.selected_row = 0
                    self.show_feedback(feedback.text, not feedback.ok)
                    return
                key_map = {
                    "Language": "language",
                    "Keyboard": "keyboard",
                    "Timezone": "timezone",
                    "Updates": "updates",
                    "Theme": "theme",
                    "Screen Timeout": "screen_timeout",
                    "Display Sleep": "display_sleep",
                }
                key = key_map.get(page.title, page.title.lower().replace(" ", "_"))
                feedback = self.backend.apply_selector(key, option.value)
                self.stack.pop()
                self.selected_row = 0
                self.show_feedback(feedback.text, not feedback.ok)
                return

        rows = self.current_rows()
        if not rows:
            return
        if self.selected_row >= len(rows):
            self.selected_row = 0
        row = rows[self.selected_row]
        if row.disabled:
            self.show_feedback(f"{row.value}", True)
            return
        if row.kind == "toggle":
            feedback = self.backend.toggle(row.key, not row.toggle_on)
            self.show_feedback(feedback.text, not feedback.ok)
            return
        if row.kind == "action":
            if row.key in {"reboot", "shutdown"}:
                self.stack.append(StackPage(row.label, kind="confirm", confirm_action=row.key, message=f"{row.label}? This will affect the device."))
                self.selected_row = 0
            else:
                feedback = self.backend.action(row.key)
                self.show_feedback(feedback.text, not feedback.ok)
            return
        if row.arrow:
            self.push_selector(row)

    def adjust_slider(self, delta: int) -> bool:
        rows = self.current_rows()
        if self.stack or not rows:
            return False
        row = rows[self.selected_row]
        if row.kind != "slider" or row.disabled:
            return False
        feedback = self.backend.set_slider(row.key, row.slider_value + delta)
        self.show_feedback(feedback.text, not feedback.ok)
        return True

    def handle_text_input(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if not self.stack or self.stack[-1].kind not in {"text", "password"}:
            return False
        page = self.stack[-1]
        if keyval == Gdk.KEY_BackSpace:
            self.stack[-1] = StackPage(
                page.title,
                kind=page.kind,
                field_key=page.field_key,
                text_value=page.text_value[:-1],
                password_target=page.password_target,
            )
            return True
        char = Gdk.keyval_to_unicode(keyval)
        if char and 32 <= char <= 126 and not (state & Gdk.ModifierType.CONTROL_MASK):
            self.stack[-1] = StackPage(
                page.title,
                kind=page.kind,
                field_key=page.field_key,
                text_value=(page.text_value + chr(char))[:64],
                password_target=page.password_target,
            )
            return True
        return False

    def cancel(self) -> bool:
        if self.stack:
            self.stack.pop()
            self.selected_row = 0
            self.focus_area = "detail"
            return True
        if self.focus_area == "detail":
            self.focus_area = "sidebar"
            self.selected_row = 0
            return True
        return False

    def go_category(self) -> bool:
        if self.stack:
            self.stack.clear()
        changed = self.focus_area != "sidebar"
        self.focus_area = "sidebar"
        self.selected_row = 0
        return changed

    def enter(self) -> None:
        if self.focus_area == "sidebar" and not self.stack:
            self.focus_area = "detail"
            self.selected_row = 0
            return
        self.activate_row()

    def move_selection(self, delta: int) -> None:
        if self.focus_area == "sidebar" and not self.stack:
            self.category_index = (self.category_index + delta) % len(CATEGORIES)
            self.selected_row = 0
            return
        count = self.current_count()
        self.selected_row = (self.selected_row + delta) % max(1, count)

    def _on_key_pressed(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C) and not self.stack and not (state & Gdk.ModifierType.CONTROL_MASK):
            handled = self.go_category()
            if handled:
                self.queue_draw()
            return handled
        if keyval in (Gdk.KEY_b, Gdk.KEY_B) and not self.stack and not (state & Gdk.ModifierType.CONTROL_MASK):
            if self.cancel():
                self.queue_draw()
                return True
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
                return True
            return False
        if self.handle_text_input(keyval, state):
            self.queue_draw()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C) and not (state & Gdk.ModifierType.CONTROL_MASK):
            handled = self.go_category()
            if handled:
                self.queue_draw()
            return handled
        if keyval in (Gdk.KEY_b, Gdk.KEY_B) and not (state & Gdk.ModifierType.CONTROL_MASK):
            if self.cancel():
                self.queue_draw()
                return True
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                root.close()
                return True
            return False
        if keyval == Gdk.KEY_Tab:
            return False
        elif keyval in (Gdk.KEY_Down,):
            self.move_selection(1)
        elif keyval in (Gdk.KEY_Up,):
            self.move_selection(-1)
        elif keyval in (Gdk.KEY_Left,):
            if self.adjust_slider(-5):
                self.queue_draw()
                return True
            if not self.cancel():
                return False
        elif keyval in (Gdk.KEY_Right,):
            if self.focus_area == "sidebar" and not self.stack:
                self.enter()
                self.queue_draw()
                return True
            if self.adjust_slider(5):
                self.queue_draw()
                return True
            rows = self.current_rows()
            if self.focus_area == "detail" and rows and not self.stack and rows[self.selected_row].arrow:
                self.push_selector(rows[self.selected_row])
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.enter()
        elif keyval in (Gdk.KEY_Escape, Gdk.KEY_BackSpace):
            if not self.cancel():
                return False
        else:
            return False
        self.queue_draw()
        return True


class SettingsApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.cardputerzero.defaultapps.settings")

    def do_activate(self) -> None:
        load_css()
        window = Gtk.ApplicationWindow(application=self, title="Settings")
        window.set_default_size(WIDTH, HEIGHT)
        window.set_size_request(WIDTH, HEIGHT)
        window.set_resizable(False)
        window.set_decorated(False)
        canvas = SettingsCanvas()
        window.set_child(canvas)
        window.present()
        GLib.idle_add(canvas.grab_focus)


def run(argv: list[str] | None = None) -> int:
    app = SettingsApplication()
    return app.run(argv or [])
