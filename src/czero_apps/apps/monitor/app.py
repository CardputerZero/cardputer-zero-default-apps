from __future__ import annotations

import os
import re
import shutil
import subprocess
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

PANEL_X = 4
PANEL_Y = 4
PANEL_W = 312
PANEL_H = 142
TITLE_H = 20

ZERO_PAPER = (0xE9 / 255, 0xE4 / 255, 0xD5 / 255)
PANEL_CREAM = (0xF4 / 255, 0xF0 / 255, 0xE6 / 255)
ICON_WELL = (0xF8 / 255, 0xF4 / 255, 0xEA / 255)
INK_BLACK = (0x17 / 255, 0x17 / 255, 0x17 / 255)
LINE_BLACK = (0x2A / 255, 0x2A / 255, 0x2A / 255)
MUTED_TEXT = (0x6E / 255, 0x6A / 255, 0x61 / 255)
ACCENT_ORANGE = (0xE6 / 255, 0x6A / 255, 0x2C / 255)
OK_GREEN = (0x3A / 255, 0x7D / 255, 0x44 / 255)
HARD_SHADOW = (0xBD / 255, 0xB5 / 255, 0xA4 / 255)
TITLE_FILL = (0xF0 / 255, 0xD2 / 255, 0xBD / 255)
SELECT_FILL = (0xFB / 255, 0xEE / 255, 0xDD / 255)


TabKind = Literal["cpu", "ram", "disk", "network", "temperature"]


@dataclass(frozen=True)
class InfoItem:
    label: str
    value: str
    icon: str = "dot"
    ok: bool = False


@dataclass(frozen=True)
class HeroData:
    value: str
    caption: str
    size: int = 28


@dataclass(frozen=True)
class UsageData:
    usage: int
    segmented: bool = False


@dataclass(frozen=True)
class NetworkAddress:
    label: str
    interface: str
    address: str
    state: str


@dataclass(frozen=True)
class ProcessItem:
    pid: str
    name: str
    cpu: str
    mem: str
    cpu_value: float
    mem_value: float


@dataclass(frozen=True)
class MonitorTab:
    name: str
    hero: HeroData | None
    content_kind: TabKind
    usage_bar: UsageData | None
    info: tuple[InfoItem, ...]
    addresses: tuple[NetworkAddress, ...] = ()
    processes: tuple[ProcessItem, ...] = ()


@dataclass(frozen=True)
class CpuTimes:
    idle: int
    total: int


@dataclass(frozen=True)
class NetBytes:
    rx: int
    tx: int
    stamp: float


def run_command(args: list[str], timeout: int = 2) -> str:
    try:
        completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip()


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def fmt_bytes(kib: int) -> str:
    mib = kib / 1024
    if mib >= 1024:
        return f"{mib / 1024:.1f} GB"
    return f"{mib:.0f} MB"


def compact_unit(value: str) -> str:
    return value.replace(" GHz", "G").replace(" GB", "GB").replace(" MB", "MB").replace(" KB", "KB")


def fmt_rate(bytes_per_second: float) -> str:
    kib = bytes_per_second / 1024
    if kib >= 1024:
        return f"{kib / 1024:.1f} MB/s"
    return f"{kib:.0f} KB/s"


def read_cpu_times() -> CpuTimes | None:
    try:
        parts = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        values = [int(value) for value in parts]
    except (OSError, ValueError, IndexError):
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return CpuTimes(idle=idle, total=sum(values))


def cpu_percent(prev: CpuTimes | None, current: CpuTimes | None) -> int:
    if prev is None or current is None:
        return 0
    total_delta = current.total - prev.total
    idle_delta = current.idle - prev.idle
    if total_delta <= 0:
        return 0
    return max(0, min(100, round((total_delta - idle_delta) * 100 / total_delta)))


def read_load() -> str:
    try:
        return "/".join(Path("/proc/loadavg").read_text().split()[:3])
    except OSError:
        return "unavailable"


def read_uptime() -> str:
    try:
        seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return "unavailable"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}"
    return f"{hours:02d}:{minutes:02d}"


def read_cpu_freq() -> str:
    value = read_int(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"))
    if value is None:
        return "unavailable"
    return f"{value / 1_000_000:.2f}G"


def read_memory() -> tuple[int, str, str, str, str]:
    mem: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.split()[0])
    except (OSError, ValueError, IndexError):
        return 0, "n/a", "n/a", "n/a", "n/a"
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = max(0, total - available)
    free = available
    usage = round(used * 100 / total) if total else 0
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)
    swap = f"{compact_unit(fmt_bytes(swap_used))}/{compact_unit(fmt_bytes(swap_total))}" if swap_total else "0MB"
    return usage, fmt_bytes(used), fmt_bytes(total), fmt_bytes(free), swap


def read_disk() -> tuple[int, str, str, str, str]:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return 0, "n/a", "n/a", "n/a", "/"
    used = usage.used // 1024
    total = usage.total // 1024
    free = usage.free // 1024
    pct = round(usage.used * 100 / usage.total) if usage.total else 0
    return pct, fmt_bytes(used), fmt_bytes(total), fmt_bytes(free), "/"


def iface_label(name: str) -> str | None:
    if name == "lo":
        return None
    if name.startswith(("wl", "wlan")) or Path(f"/sys/class/net/{name}/wireless").exists():
        return "WiFi"
    if name.startswith(("en", "eth")):
        return "Ethernet"
    return None


def interface_ipv4_map() -> dict[str, str]:
    output = run_command(["ip", "-o", "-4", "addr", "show", "scope", "global"])
    addresses: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"\d+:\s+(\S+)\s+inet\s+([0-9.]+)/\d+", line)
        if not match:
            continue
        iface, address = match.groups()
        addresses[iface] = address
    return addresses


def read_network_addresses() -> tuple[NetworkAddress, ...]:
    ipv4 = interface_ipv4_map()
    addresses: list[NetworkAddress] = []
    for iface_path in sorted(Path("/sys/class/net").iterdir(), key=lambda item: item.name):
        iface = iface_path.name
        label = iface_label(iface)
        if not label:
            continue
        state_path = Path(f"/sys/class/net/{iface}/operstate")
        try:
            state = state_path.read_text().strip()
        except OSError:
            state = "unknown"
        addresses.append(NetworkAddress(label, iface, ipv4.get(iface, "no IPv4"), state))
    order = {"WiFi": 0, "Ethernet": 1}
    return tuple(sorted(addresses, key=lambda item: order.get(item.label, 9)))


def read_processes(sort: Literal["cpu", "mem"]) -> tuple[ProcessItem, ...]:
    sort_arg = "-%cpu" if sort == "cpu" else "-rss"
    output = run_command(["ps", "-eo", "pid,comm,%cpu,%mem,rss", f"--sort={sort_arg}"])
    items: list[ProcessItem] = []
    for line in output.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        pid, comm, cpu, mem = parts[:4]
        if comm == "ps":
            continue
        try:
            cpu_value = float(cpu)
        except ValueError:
            cpu_value = 0.0
        try:
            mem_value = float(mem)
        except ValueError:
            mem_value = 0.0
        items.append(ProcessItem(pid=pid, name=comm, cpu=f"{cpu}%", mem=f"{mem}%", cpu_value=cpu_value, mem_value=mem_value))
        if len(items) == 4:
            break
    return tuple(items)


def read_net_bytes() -> NetBytes:
    rx = 0
    tx = 0
    for iface_path in Path("/sys/class/net").iterdir():
        label = iface_label(iface_path.name)
        if not label:
            continue
        rx += read_int(iface_path / "statistics" / "rx_bytes") or 0
        tx += read_int(iface_path / "statistics" / "tx_bytes") or 0
    return NetBytes(rx=rx, tx=tx, stamp=time.monotonic())


def net_rates(prev: NetBytes | None, current: NetBytes) -> tuple[str, str, int]:
    if prev is None or current.stamp <= prev.stamp:
        return "0 KB/s", "0 KB/s", 0
    elapsed = current.stamp - prev.stamp
    down = max(0, current.rx - prev.rx) / elapsed
    up = max(0, current.tx - prev.tx) / elapsed
    activity = min(100, round((down + up) / 2048))
    return fmt_rate(down), fmt_rate(up), activity


def read_temperatures() -> tuple[int, int, int, str]:
    values: list[int] = []
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        value = read_int(path)
        if value is not None:
            values.append(round(value / 1000))
    if not values:
        vcgencmd = run_command(["vcgencmd", "measure_temp"])
        match = re.search(r"([0-9.]+)", vcgencmd)
        if match:
            values.append(round(float(match.group(1))))
    current = values[0] if values else 0
    soc = values[0] if values else current
    cpu = values[1] if len(values) > 1 else current
    peak = max(values) if values else current
    status = "Warm" if current >= 70 else "Normal"
    return current, cpu, soc, peak, status


class SystemDataProvider:
    def __init__(self) -> None:
        self.prev_cpu = read_cpu_times()
        self.prev_net = read_net_bytes()
        self.cpu_history: list[int] = [0] * 30
        self.net_history: list[int] = [0] * 30
        self.temp_history: list[int] = [0] * 16

    def tabs(self) -> tuple[MonitorTab, ...]:
        current_cpu = read_cpu_times()
        cpu_usage = cpu_percent(self.prev_cpu, current_cpu)
        self.prev_cpu = current_cpu
        if cpu_usage == 0:
            load_hint = Path("/proc/loadavg").read_text().split()[0] if Path("/proc/loadavg").exists() else "0"
            try:
                cpu_usage = min(100, round(float(load_hint) * 25))
            except ValueError:
                cpu_usage = 0
        self.cpu_history = (self.cpu_history + [cpu_usage])[-30:]

        mem_usage, mem_used, mem_total, mem_free, swap = read_memory()
        disk_usage, disk_used, disk_total, disk_free, mount = read_disk()
        net_now = read_net_bytes()
        down_rate, up_rate, net_activity = net_rates(self.prev_net, net_now)
        self.prev_net = net_now
        self.net_history = (self.net_history + [net_activity])[-30:]
        addresses = read_network_addresses()
        current_temp, cpu_temp, soc_temp, peak_temp, temp_status = read_temperatures()
        self.temp_history = (self.temp_history + [current_temp])[-16:]

        return (
            MonitorTab(
                "CPU",
                HeroData(f"{cpu_usage}%", "CPU Usage", 31),
                "cpu",
                None,
                (
                    InfoItem("Load", read_load(), "load"),
                    InfoItem("Freq", read_cpu_freq(), "chip"),
                    InfoItem("Cores", str(os.cpu_count() or 0), "grid"),
                    InfoItem("Uptime", read_uptime(), "clock"),
                ),
                processes=read_processes("cpu"),
            ),
            MonitorTab(
                "RAM",
                HeroData(f"{mem_usage}%", "RAM Usage", 31),
                "ram",
                None,
                (
                    InfoItem("Used", mem_used, "memory"),
                    InfoItem("Total", mem_total, "grid"),
                    InfoItem("Free", mem_free, "dot"),
                    InfoItem("Swap", swap, "swap"),
                ),
                processes=read_processes("mem"),
            ),
            MonitorTab(
                "Disk",
                HeroData(f"{disk_usage}%", "Disk Usage", 31),
                "disk",
                UsageData(disk_usage, False),
                (
                    InfoItem("Used", disk_used, "disk"),
                    InfoItem("Total", disk_total, "grid"),
                    InfoItem("Free", disk_free, "dot"),
                    InfoItem("Mount", mount, "mount"),
                ),
            ),
            MonitorTab(
                "Network",
                None,
                "network",
                None,
                (
                    InfoItem("Down", down_rate, "down"),
                    InfoItem("Up", up_rate, "up"),
                    InfoItem("Links", str(len(addresses)), "port"),
                    InfoItem("State", "Online" if addresses else "Offline", "check", bool(addresses)),
                ),
                addresses,
            ),
            MonitorTab(
                "Temperature",
                HeroData(f"{current_temp}C", "SoC Temp", 31),
                "temperature",
                None,
                (
                    InfoItem("CPU", f"{cpu_temp}C", "thermal"),
                    InfoItem("SoC", f"{soc_temp}C", "chip"),
                    InfoItem("Peak", f"{peak_temp}C", "up"),
                    InfoItem("Status", temp_status, "check", temp_status == "Normal"),
                ),
            ),
        )


def set_color(ctx: cairo.Context, color: tuple[float, float, float]) -> None:
    ctx.set_source_rgb(*color)


def configure_crisp(ctx: cairo.Context) -> None:
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_NONE)
    ctx.set_font_options(options)


def fill_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float]) -> None:
    set_color(ctx, color)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def stroke_rect(ctx: cairo.Context, x: int, y: int, w: int, h: int, color: tuple[float, float, float] = LINE_BLACK) -> None:
    set_color(ctx, color)
    ctx.set_line_width(1)
    ctx.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
    ctx.stroke()


def line(ctx: cairo.Context, x1: int, y1: int, x2: int, y2: int, color: tuple[float, float, float] = LINE_BLACK) -> None:
    set_color(ctx, color)
    ctx.set_line_width(1)
    ctx.move_to(x1 + 0.5, y1 + 0.5)
    ctx.line_to(x2 + 0.5, y2 + 0.5)
    ctx.stroke()


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


def draw_icon(ctx: cairo.Context, icon: str, x: int, y: int) -> None:
    set_color(ctx, OK_GREEN if icon == "check" else INK_BLACK)
    ctx.set_line_width(1)
    if icon == "load":
        ctx.move_to(x, y + 8)
        ctx.line_to(x + 4, y + 4)
        ctx.line_to(x + 8, y + 7)
        ctx.line_to(x + 12, y + 2)
        ctx.stroke()
    elif icon == "chip":
        stroke_rect(ctx, x + 2, y + 2, 10, 10)
        for off in (0, 4, 8):
            line(ctx, x, y + 3 + off, x + 2, y + 3 + off)
            line(ctx, x + 12, y + 3 + off, x + 14, y + 3 + off)
    elif icon == "grid":
        for yy in (1, 8):
            for xx in (1, 8):
                stroke_rect(ctx, x + xx, y + yy, 5, 5)
    elif icon == "clock":
        ctx.arc(x + 7, y + 7, 6, 0, 6.283)
        ctx.stroke()
        line(ctx, x + 7, y + 7, x + 7, y + 3)
        line(ctx, x + 7, y + 7, x + 10, y + 9)
    elif icon in {"down", "up"}:
        direction = 1 if icon == "down" else -1
        line(ctx, x + 7, y + (2 if direction == 1 else 12), x + 7, y + (11 if direction == 1 else 3))
        ctx.move_to(x + 3, y + (8 if direction == 1 else 6))
        ctx.line_to(x + 7, y + (12 if direction == 1 else 2))
        ctx.line_to(x + 11, y + (8 if direction == 1 else 6))
        ctx.stroke()
    elif icon == "signal":
        for index, h in enumerate((3, 6, 9, 12)):
            stroke_rect(ctx, x + index * 3, y + 13 - h, 2, h)
    elif icon == "port":
        stroke_rect(ctx, x + 1, y + 3, 12, 8)
        line(ctx, x + 4, y + 11, x + 4, y + 14)
        line(ctx, x + 10, y + 11, x + 10, y + 14)
    elif icon == "disk":
        stroke_rect(ctx, x + 1, y + 3, 12, 9)
        line(ctx, x + 3, y + 6, x + 11, y + 6)
        ctx.arc(x + 10, y + 9, 1, 0, 6.283)
        ctx.stroke()
    elif icon == "mount":
        stroke_rect(ctx, x + 3, y + 1, 8, 12)
        line(ctx, x + 5, y + 13, x + 9, y + 13)
    elif icon == "thermal":
        stroke_rect(ctx, x + 5, y + 2, 4, 8)
        ctx.arc(x + 7, y + 11, 4, 0, 6.283)
        ctx.stroke()
    elif icon == "check":
        ctx.move_to(x + 2, y + 8)
        ctx.line_to(x + 6, y + 12)
        ctx.line_to(x + 13, y + 2)
        ctx.stroke()
    else:
        ctx.arc(x + 7, y + 7, 2, 0, 6.283)
        ctx.stroke()


class UsageBar:
    def __init__(self, data: UsageData) -> None:
        self.data = data

    def draw(self, ctx: cairo.Context, x: int, y: int, w: int, h: int) -> None:
        fill_rect(ctx, x, y, w, h, ICON_WELL)
        stroke_rect(ctx, x, y, w, h)
        bar_x = x + 9
        bar_y = y + 15
        bar_w = w - 18
        bar_h = 18
        fill_rect(ctx, bar_x, bar_y, bar_w, bar_h, PANEL_CREAM)
        stroke_rect(ctx, bar_x, bar_y, bar_w, bar_h)
        used_w = int((bar_w - 2) * self.data.usage / 100)
        if self.data.segmented:
            segments = 12
            gap = 2
            seg_w = (bar_w - 2 - gap * (segments - 1)) // segments
            for index in range(segments):
                sx = bar_x + 1 + index * (seg_w + gap)
                filled = index < round(segments * self.data.usage / 100)
                fill_rect(ctx, sx, bar_y + 3, seg_w, bar_h - 6, ACCENT_ORANGE if filled else PANEL_CREAM)
                stroke_rect(ctx, sx, bar_y + 3, seg_w, bar_h - 6, LINE_BLACK)
        else:
            fill_rect(ctx, bar_x + 1, bar_y + 1, used_w, bar_h - 2, ACCENT_ORANGE)
        text(ctx, "Used", bar_x, y + 11, MUTED_TEXT, 8, cairo.FONT_WEIGHT_BOLD)
        text_right(ctx, f"{self.data.usage}%", bar_x + bar_w, y + 11, ACCENT_ORANGE, 9)


class MetricHero:
    def __init__(self, data: HeroData) -> None:
        self.data = data

    def draw(self, ctx: cairo.Context, x: int, y: int, w: int, h: int) -> None:
        if self.data.size <= 14:
            text(ctx, self.data.value, x + 5, y + 30, INK_BLACK, self.data.size, cairo.FONT_WEIGHT_BOLD)
        else:
            text(ctx, self.data.value, x + 11, y + 44, INK_BLACK, self.data.size, cairo.FONT_WEIGHT_BOLD)
        text(ctx, self.data.caption, x + 14, y + h - 8, INK_BLACK, 10)


class MonitorPanel:
    def __init__(self) -> None:
        pass

    def draw(self, ctx: cairo.Context, tab: MonitorTab) -> None:
        panel(ctx, PANEL_X, PANEL_Y, PANEL_W, PANEL_H)
        fill_rect(ctx, PANEL_X + 1, PANEL_Y + 1, PANEL_W - 2, TITLE_H - 1, TITLE_FILL)
        text(ctx, "System Monitor", PANEL_X + 9, PANEL_Y + 14, INK_BLACK, 11, cairo.FONT_WEIGHT_BOLD)
        text_right(ctx, tab.name, PANEL_X + PANEL_W - 10, PANEL_Y + 14, INK_BLACK, 11, cairo.FONT_WEIGHT_BOLD)
        line(ctx, PANEL_X, PANEL_Y + TITLE_H, PANEL_X + PANEL_W - 1, PANEL_Y + TITLE_H)

        if tab.content_kind == "network":
            self.draw_network(ctx, tab)
        elif tab.content_kind == "temperature":
            self.draw_temperature(ctx, tab)
        else:
            self.draw_metric_page(ctx, tab)

    def draw_metric_page(self, ctx: cairo.Context, tab: MonitorTab) -> None:
        content_y = PANEL_Y + TITLE_H + 1
        if tab.hero:
            MetricHero(tab.hero).draw(ctx, PANEL_X + 8, content_y + 2, 82, 70)
        line(ctx, PANEL_X + 91, content_y + 8, PANEL_X + 91, content_y + 68, MUTED_TEXT)
        if tab.processes:
            self.draw_process_list(ctx, tab)
        elif tab.usage_bar:
            chart_x = PANEL_X + 99
            chart_y = content_y + 11
            chart_w = 204
            chart_h = 48
            UsageBar(tab.usage_bar).draw(ctx, chart_x, chart_y, chart_w, chart_h)
        info_y = PANEL_Y + 96
        line(ctx, PANEL_X + 1, info_y - 5, PANEL_X + PANEL_W - 2, info_y - 5, HARD_SHADOW)
        self.draw_info_grid(ctx, tab.info, PANEL_X + 8, info_y, PANEL_W - 16, 40)

    def draw_process_list(self, ctx: cairo.Context, tab: MonitorTab) -> None:
        x = PANEL_X + 101
        y = PANEL_Y + TITLE_H + 8
        w = PANEL_W - 111
        fill_rect(ctx, x, y, w, 57, ICON_WELL)
        stroke_rect(ctx, x, y, w, 57)
        title = "Top CPU Processes" if tab.content_kind == "cpu" else "Top RAM Processes"
        text(ctx, title, x + 6, y + 11, MUTED_TEXT, 8, cairo.FONT_WEIGHT_BOLD)
        line(ctx, x + 1, y + 14, x + w - 2, y + 14, HARD_SHADOW)
        max_value = max(
            (proc.cpu_value if tab.content_kind == "cpu" else proc.mem_value for proc in tab.processes),
            default=1.0,
        )
        for index, proc in enumerate(tab.processes[:4]):
            row_y = y + 24 + index * 8
            value = proc.cpu if tab.content_kind == "cpu" else proc.mem
            raw_value = proc.cpu_value if tab.content_kind == "cpu" else proc.mem_value
            text(ctx, fit_text(proc.name, 11), x + 6, row_y, INK_BLACK, 8)
            bar_x = x + 66
            bar_w = 79
            fill_rect(ctx, bar_x, row_y - 6, bar_w, 5, PANEL_CREAM)
            stroke_rect(ctx, bar_x, row_y - 6, bar_w, 5, HARD_SHADOW)
            fill_w = max(1, int((raw_value / max_value) * (bar_w - 2))) if raw_value > 0 else 0
            if fill_w:
                fill_rect(ctx, bar_x + 1, row_y - 5, fill_w, 3, ACCENT_ORANGE)
            text_right(ctx, value, x + w - 6, row_y, ACCENT_ORANGE, 8)

    def draw_network(self, ctx: cairo.Context, tab: MonitorTab) -> None:
        x = PANEL_X + 10
        y = PANEL_Y + TITLE_H + 11
        text(ctx, "Addresses", x, y, INK_BLACK, 10, cairo.FONT_WEIGHT_BOLD)
        row_y = y + 12
        if not tab.addresses:
            text(ctx, "No WiFi or Ethernet IPv4 address", x, row_y + 14, MUTED_TEXT, 9)
        for address in tab.addresses[:3]:
            fill_rect(ctx, x, row_y, PANEL_W - 20, 24, ICON_WELL)
            stroke_rect(ctx, x, row_y, PANEL_W - 20, 24)
            draw_icon(ctx, "signal" if address.label == "WiFi" else "port", x + 7, row_y + 5)
            text(ctx, address.label.upper(), x + 27, row_y + 10, ACCENT_ORANGE, 8, cairo.FONT_WEIGHT_BOLD)
            text(ctx, address.interface, x + 78, row_y + 10, MUTED_TEXT, 8)
            text(ctx, address.address, x + 27, row_y + 21, INK_BLACK, 10, cairo.FONT_WEIGHT_BOLD)
            text_right(ctx, address.state, x + PANEL_W - 27, row_y + 21, MUTED_TEXT, 8)
            row_y += 29
        self.draw_info_grid(ctx, tab.info, PANEL_X + 8, PANEL_Y + 102, PANEL_W - 16, 34)

    def draw_temperature(self, ctx: cairo.Context, tab: MonitorTab) -> None:
        content_y = PANEL_Y + TITLE_H + 1
        if tab.hero:
            MetricHero(tab.hero).draw(ctx, PANEL_X + 8, content_y + 4, 82, 68)
        line(ctx, PANEL_X + 91, content_y + 8, PANEL_X + 91, content_y + 68, MUTED_TEXT)
        x = PANEL_X + 105
        y = content_y + 9
        for index, item in enumerate(tab.info):
            row_y = y + index * 16
            draw_icon(ctx, item.icon, x, row_y - 6)
            text(ctx, item.label, x + 21, row_y + 4, MUTED_TEXT, 8)
            value_color = OK_GREEN if item.ok else INK_BLACK
            text(ctx, item.value, x + 86, row_y + 4, value_color, 10, cairo.FONT_WEIGHT_BOLD)
        fill_rect(ctx, PANEL_X + 9, PANEL_Y + 107, PANEL_W - 18, 23, ICON_WELL)
        stroke_rect(ctx, PANEL_X + 9, PANEL_Y + 107, PANEL_W - 18, 23)
        text(ctx, "Simple temperature summary. No chart.", PANEL_X + 16, PANEL_Y + 122, MUTED_TEXT, 9)

    def draw_info_grid(self, ctx: cairo.Context, items: tuple[InfoItem, ...], x: int, y: int, w: int, h: int) -> None:
        col_w = w // 2
        row_h = h // 2
        for index, item in enumerate(items):
            col = index % 2
            row = index // 2
            item_x = x + col * col_w
            item_y = y + row * row_h
            if col:
                line(ctx, item_x - 5, y + 1, item_x - 5, y + h - 3, MUTED_TEXT)
            if row:
                line(ctx, x, item_y - 2, x + w - 1, item_y - 2, HARD_SHADOW)
            text(ctx, item.label, item_x, item_y + 11, INK_BLACK, 9, cairo.FONT_WEIGHT_BOLD)
            value_color = OK_GREEN if item.ok else INK_BLACK
            value = compact_unit(item.value)
            text_right(ctx, fit_text(value, 14), item_x + col_w - 9, item_y + 11, value_color, 9)


class BottomTabBar:
    def draw(self, ctx: cairo.Context, selected_tab: int) -> None:
        y = MAIN_H
        fill_rect(ctx, 0, y, WIDTH, BOTTOM_H, ZERO_PAPER)
        line(ctx, 0, y, WIDTH, y)
        keycap(ctx, 5, y + 3, "TAB", 29)
        tab_x = 43
        widths = (29, 29, 32, 31, 36)
        labels = ("CPU", "RAM", "DSK", "NET", "TEMP")
        for index, (label, width) in enumerate(zip(labels, widths)):
            if index == selected_tab:
                fill_rect(ctx, tab_x, y + 3, width, 13, SELECT_FILL)
                stroke_rect(ctx, tab_x, y + 3, width, 13, ACCENT_ORANGE)
                text(ctx, label, tab_x + 4, y + 13, ACCENT_ORANGE, 8, cairo.FONT_WEIGHT_BOLD)
            else:
                text(ctx, label, tab_x + 4, y + 13, INK_BLACK, 8)
            tab_x += width + 4
        text(ctx, f"{selected_tab + 1}/5", 239, y + 13, INK_BLACK, 8)
        keycap(ctx, 277, y + 3, "ESC", 34)


class MonitorCanvas(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.selected_tab = 0
        self.provider = SystemDataProvider()
        self.tabs = self.provider.tabs()
        self.panel = MonitorPanel()
        self.bottom_bar = BottomTabBar()
        self.set_content_width(WIDTH)
        self.set_content_height(HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_focusable(True)
        self.set_draw_func(self._draw)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        GLib.timeout_add_seconds(2, self.refresh)

    def refresh(self) -> bool:
        self.tabs = self.provider.tabs()
        self.queue_draw()
        return True

    def _draw(self, _area: Gtk.DrawingArea, ctx: cairo.Context, _width: int, _height: int) -> None:
        configure_crisp(ctx)
        fill_rect(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
        self.panel.draw(ctx, self.tabs[self.selected_tab])
        self.bottom_bar.draw(ctx, self.selected_tab)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_Right):
            self.selected_tab = (self.selected_tab + 1) % len(self.tabs)
        elif keyval in (Gdk.KEY_Left,):
            self.selected_tab = (self.selected_tab - 1) % len(self.tabs)
        else:
            return False
        self.queue_draw()
        return True


class SystemMonitorApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.cardputerzero.defaultapps.monitor")

    def do_activate(self) -> None:
        load_css()
        window = Gtk.ApplicationWindow(application=self, title="System Monitor")
        window.set_default_size(WIDTH, HEIGHT)
        window.set_size_request(WIDTH, HEIGHT)
        window.set_resizable(False)
        window.set_decorated(False)
        canvas = MonitorCanvas()
        window.set_child(canvas)
        window.present()
        GLib.idle_add(canvas.grab_focus)


def run(argv: list[str] | None = None) -> int:
    app = SystemMonitorApp()
    return app.run(argv or [])
