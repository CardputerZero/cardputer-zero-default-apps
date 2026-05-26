from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cairo

from czero_apps.ui.gtk import Gdk, GLib, Gtk
from czero_apps.ui.theme import load_css


WIDTH = 320
HEIGHT = 170
MAIN_H = 150
BOTTOM_H = 20

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
SELECT_FILL = "#FBEEDE"
TITLE_FILL = "#F0D2BD"
SOFT_LINE = "#DCD5C3"

RESULT_LINE_WIDTH = 59
RESULT_BODY_WIDTH = 55
RESULT_VISIBLE_LINES = 15

Mode = Literal["compose", "confirm_transcript", "running", "result", "error", "settings", "edit_config"]
RobotMode = Literal["SAFE", "EDIT", "FULL"]

MODE_ORDER: tuple[RobotMode, ...] = ("SAFE", "EDIT", "FULL")
MODE_TOOLS: dict[RobotMode, tuple[str, ...]] = {
    "SAFE": ("read", "grep", "find", "ls"),
    "EDIT": ("read", "grep", "find", "ls", "edit", "write"),
    "FULL": ("read", "grep", "find", "ls", "edit", "write", "bash"),
}

DEFAULT_CONFIG = {
    "mode": "EDIT",
    "cwd": "home",
    "pi_bin": "pi",
    "provider": "",
    "model": "",
    "session_dir": "default",
    "persist_session": True,
    "offline": False,
    "record_seconds": 5,
    "recorder": "auto",
    "transcribe_model": "gpt-4o-mini-transcribe",
    "theme": "zero-paper-robot",
}


def config_path() -> Path:
    return Path.home() / ".config" / "cardputer-zero" / "default-apps" / "robot.json"


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


def resolve_cwd(value: str) -> Path:
    if value == "home" or not value:
        return Path.home()
    return Path(value).expanduser()


def fit_text(value: str, limit: int) -> str:
    value = value.replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    if limit <= 2:
        return value[:limit]
    return value[: limit - 2] + ".."


def wrap_text(value: str, width: int, max_lines: int = 0) -> list[str]:
    words = value.replace("\r", "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = [word[index : index + width] for index in range(0, len(word), width)] or [word]
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= width:
                current += " " + piece
            else:
                lines.append(current)
                if max_lines and len(lines) >= max_lines:
                    return lines
                current = piece
    if current and (not max_lines or len(lines) < max_lines):
        lines.append(current)
    return lines or [""]


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)


def color(ctx: cairo.Context, value: str) -> None:
    ctx.set_source_rgb(*hex_to_rgb(value))


def fill(ctx: cairo.Context, x: int, y: int, w: int, h: int, value: str) -> None:
    color(ctx, value)
    ctx.rectangle(x, y, w, h)
    ctx.fill()


def stroke(ctx: cairo.Context, x: int, y: int, w: int, h: int, value: str = LINE_BLACK) -> None:
    color(ctx, value)
    ctx.set_line_width(1)
    ctx.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
    ctx.stroke()


def line(ctx: cairo.Context, x1: int, y1: int, x2: int, y2: int, value: str = LINE_BLACK) -> None:
    color(ctx, value)
    ctx.set_line_width(1)
    ctx.move_to(x1 + 0.5, y1 + 0.5)
    ctx.line_to(x2 + 0.5, y2 + 0.5)
    ctx.stroke()


def text(
    ctx: cairo.Context,
    value: str,
    x: int,
    y: int,
    fg: str = INK_BLACK,
    size: int = 8,
    bold: bool = False,
) -> None:
    color(ctx, fg)
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.move_to(x, y)
    ctx.show_text(value)


def text_center(ctx: cairo.Context, value: str, cx: int, y: int, fg: str = INK_BLACK, size: int = 8, bold: bool = False) -> None:
    color(ctx, fg)
    ctx.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ext = ctx.text_extents(value)
    ctx.move_to(cx - ext.width / 2, y)
    ctx.show_text(value)


def draw_key(ctx: cairo.Context, x: int, y: int, label: str, w: int, accent_first: bool = False) -> None:
    fill(ctx, x + 1, y + 13, w, 2, HARD_SHADOW)
    fill(ctx, x, y, w, 14, ICON_WELL)
    stroke(ctx, x, y, w, 15)
    line(ctx, x + 2, y + 11, x + w - 3, y + 11)
    if accent_first and label:
        text(ctx, label[0], x + 4, y + 10, ACCENT_ORANGE, 8, True)
        if len(label) > 1:
            text(ctx, label[1:], x + 10, y + 10, INK_BLACK, 8, True)
    else:
        text(ctx, label, x + 4, y + 10, ACCENT_ORANGE if label in {"R", "M", "C", "B"} else INK_BLACK, 8, True)


@dataclass
class AgentEvent:
    kind: str
    text: str


@dataclass(frozen=True)
class SettingsItem:
    key: str
    label: str
    value: str
    kind: Literal["choice", "text", "toggle"]
    choices: list[str] = field(default_factory=list)


@dataclass
class RobotState:
    mode: Mode = "compose"
    robot_mode: RobotMode = "EDIT"
    cwd: Path = field(default_factory=Path.home)
    prompt: str = ""
    transcript: str = ""
    status: str = "READY"
    events: list[AgentEvent] = field(default_factory=list)
    result_lines: list[str] = field(default_factory=list)
    last_message: str = ""
    error: str = ""
    scroll: int = 0
    settings_index: int = 0
    edit_key: str = ""
    edit_value: str = ""
    started_at: float = 0.0


def clean_agent_text(value: str) -> str:
    text_value = value.replace("\r", "\n")
    cleaned_lines: list[str] = []
    for raw_line in text_value.splitlines():
        line_value = raw_line.strip()
        if not line_value:
            if cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
            continue
        if line_value.startswith(("updateTheUser", "updateUser")):
            continue
        for prefix in ("updateAssistant", "update"):
            if line_value.startswith(prefix):
                line_value = line_value[len(prefix) :].strip(" :")
                break
        if line_value in {"message", "message start", "message end", "turn start", "turn end", "agent end"}:
            continue
        if line_value.startswith("message "):
            line_value = line_value[8:].strip()
        if line_value:
            cleaned_lines.append(line_value)
    while cleaned_lines and not cleaned_lines[0]:
        cleaned_lines.pop(0)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def result_position(scroll: int, total: int) -> str:
    if total <= RESULT_VISIBLE_LINES:
        return f"{total:02d}/{total:02d}"
    first = min(scroll + 1, total)
    last = min(total, scroll + RESULT_VISIBLE_LINES)
    return f"{first:02d}-{last:02d}/{total:02d}"


class PiBackend:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None

    def resolve_pi_bin(self) -> str | None:
        configured = str(self.config.get("pi_bin", "pi")).strip() or "pi"
        if os.path.sep in configured:
            return configured if os.access(configured, os.X_OK) else None
        found = shutil.which(configured)
        if found:
            return found
        if configured == "pi":
            for candidate in (
                "/usr/local/bin/pi",
                "/usr/bin/pi",
                str(Path.home() / ".npm-global" / "bin" / "pi"),
                str(Path.home() / ".local" / "bin" / "pi"),
            ):
                if os.access(candidate, os.X_OK):
                    return candidate
        return None

    def available(self) -> bool:
        return self.resolve_pi_bin() is not None

    def command(self, cwd: Path, robot_mode: RobotMode) -> list[str]:
        pi_bin = self.resolve_pi_bin() or str(self.config.get("pi_bin", "pi"))
        args = [
            pi_bin,
            "--mode",
            "rpc",
            "--tools",
            ",".join(MODE_TOOLS[robot_mode]),
        ]
        provider = str(self.config.get("provider", "")).strip()
        model = str(self.config.get("model", "")).strip()
        if provider.lower() == "default":
            provider = ""
        if model.lower() == "default":
            model = ""
        session_dir = str(self.config.get("session_dir", "")).strip()
        persist_session = bool(self.config.get("persist_session", True))
        if provider:
            args.extend(["--provider", provider])
        if model:
            args.extend(["--model", model])
        if not persist_session:
            args.append("--no-session")
        elif session_dir and session_dir != "default":
            args.extend(["--session-dir", session_dir])
        return args

    def run(self, prompt: str, cwd: Path, robot_mode: RobotMode, events: "queue.Queue[AgentEvent]") -> None:
        if not self.available():
            events.put(AgentEvent("error", "pi agent not installed. Run sudo ./install.sh or set PI BIN in settings."))
            events.put(AgentEvent("done", ""))
            return
        if not cwd.exists():
            events.put(AgentEvent("error", f"cwd not found: {cwd}"))
            events.put(AgentEvent("done", ""))
            return

        try:
            args = self.command(cwd, robot_mode)
            events.put(AgentEvent("status", f"pi {robot_mode.lower()} started"))
            completed_normally = False
            try:
                env = dict(os.environ)
                if bool(self.config.get("offline", False)):
                    env["PI_OFFLINE"] = "1"
                proc: subprocess.Popen[str] = subprocess.Popen(
                    args,
                    cwd=str(cwd),
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    bufsize=1,
                )
                self.process = proc
            except OSError as exc:
                events.put(AgentEvent("error", str(exc)))
                events.put(AgentEvent("done", ""))
                return

            assert proc.stdout is not None
            assert proc.stdin is not None
            request = {"id": "zero-robot-1", "type": "prompt", "message": prompt}
            proc.stdin.write(json.dumps(request) + "\n")
            proc.stdin.flush()
            for line_value in proc.stdout:
                kind = self._parse_jsonl(line_value, events)
                if line_value.strip():
                    self._auto_handle_rpc_request(line_value, proc)
                    if kind in {"agent_end", "done"}:
                        completed_normally = True
                        break
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            stderr = proc.stderr.read() if proc.stderr else ""
            code = proc.returncode or 0
            if code != 0 and not completed_normally:
                events.put(AgentEvent("error", stderr.strip() or f"pi exited {code}"))
            elif stderr.strip():
                events.put(AgentEvent("note", stderr.strip()))
        finally:
            self.process = None
        events.put(AgentEvent("done", ""))

    def cancel(self) -> None:
        proc = self.process
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.write(json.dumps({"id": "zero-robot-abort", "type": "abort"}) + "\n")
                proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.terminate()
        except OSError:
            pass

    def _auto_handle_rpc_request(self, line_value: str, proc: subprocess.Popen[str]) -> None:
        try:
            payload = json.loads(line_value)
        except json.JSONDecodeError:
            return
        if payload.get("type") != "extension_ui_request":
            return
        if payload.get("method") not in {"select", "confirm", "input", "editor"}:
            return
        request_id = payload.get("id")
        if not request_id or proc.stdin is None:
            return
        response = {"type": "extension_ui_response", "id": request_id, "cancelled": True}
        try:
            proc.stdin.write(json.dumps(response) + "\n")
            proc.stdin.flush()
        except OSError:
            return

    def _parse_jsonl(self, line_value: str, events: "queue.Queue[AgentEvent]") -> str:
        raw = line_value.strip()
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            events.put(AgentEvent("log", raw))
            return ""
        kind = str(payload.get("type") or payload.get("event") or "event")
        event_kind = self._map_event_kind(kind, payload if isinstance(payload, dict) else None)
        text_value = clean_agent_text(self._extract_text(payload))
        if text_value:
            events.put(AgentEvent(event_kind, text_value))
        elif event_kind in {"status", "tool", "error"}:
            events.put(AgentEvent(event_kind, kind.replace("_", " ")))
        return kind

    @staticmethod
    def _map_event_kind(kind: str, payload: dict | None = None) -> str:
        if kind == "response" and payload and payload.get("success") is False:
            return "error"
        if kind in {"agent_start", "queue_update"}:
            return "status"
        if kind in {"message", "message_update", "assistant_message"}:
            return "delta"
        if kind in {"message_start", "message_end", "turn_start", "turn_end", "agent_end"}:
            return "status"
        if kind in {"agent_response"}:
            return "final"
        if kind == "response":
            return "status"
        if kind.startswith("tool_execution"):
            return "tool"
        if kind in {"agent_end", "done"}:
            return "done"
        if "error" in kind:
            return "error"
        return kind

    @staticmethod
    def _extract_text(payload: object) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            event_type = payload.get("type")
            if event_type in {"agent_end", "message_end", "turn_end"}:
                return ""
            if event_type in {"message_start", "turn_start", "agent_start"}:
                return ""
            if event_type == "response":
                command = payload.get("command", "command")
                success = payload.get("success")
                if success is False:
                    return str(payload.get("error") or f"{command} failed")
                return f"{command} accepted"
            if event_type == "extension_ui_request":
                method = payload.get("method", "ui")
                title = payload.get("title") or payload.get("message") or method
                return f"ui {method}: {title}"
            for key in (
                "text",
                "summary",
                "content",
                "delta",
                "output",
                "result",
                "error",
                "messages",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, list):
                    text_parts = [PiBackend._extract_text(item) for item in value]
                    joined = " ".join(part for part in text_parts if part)
                    if joined:
                        return joined
            nested = (
                payload.get("assistantMessageEvent")
                or payload.get("partialResult")
                or payload.get("item")
                or payload.get("data")
                or payload.get("payload")
                or payload.get("args")
            )
            if nested is not None:
                return PiBackend._extract_text(nested)
        if isinstance(payload, list):
            return " ".join(part for item in payload if (part := PiBackend._extract_text(item)))
        return ""


class SpeechBackend:
    def __init__(self, config: dict) -> None:
        self.config = config

    def record_path(self) -> Path:
        return Path("/tmp") / "zero-robot-input.wav"

    def record(self) -> tuple[bool, str, Path | None]:
        seconds = max(1, int(self.config.get("record_seconds", 5)))
        path = self.record_path()
        recorder = str(self.config.get("recorder", "auto"))
        if recorder in {"auto", "pw-record"} and shutil.which("pw-record"):
            args = ["pw-record", "--duration", str(seconds), str(path)]
        elif recorder in {"auto", "arecord"} and shutil.which("arecord"):
            args = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(seconds), str(path)]
        else:
            return False, "recorder not available", None
        try:
            completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=seconds + 3)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc), None
        if completed.returncode != 0:
            return False, completed.stderr.strip() or "record failed", None
        return True, "recorded", path

    def transcribe(self, path: Path) -> tuple[bool, str]:
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY missing"
        try:
            from openai import OpenAI  # type: ignore
        except Exception:
            return False, "python openai package missing"
        model = str(self.config.get("transcribe_model", "gpt-4o-mini-transcribe"))
        try:
            client = OpenAI()
            with path.open("rb") as audio:
                result = client.audio.transcriptions.create(model=model, file=audio)
        except Exception as exc:
            return False, str(exc)
        text_value = getattr(result, "text", "") or ""
        return (bool(text_value.strip()), text_value.strip() or "empty transcript")

    def record_and_transcribe(self) -> tuple[bool, str]:
        ok, message, path = self.record()
        if not ok or path is None:
            return False, message
        return self.transcribe(path)


class RobotCanvas(Gtk.DrawingArea):
    def __init__(self, window: "RobotWindow") -> None:
        super().__init__()
        self.window = window
        self.set_size_request(WIDTH, HEIGHT)
        self.set_focusable(True)
        self.set_draw_func(self.draw)

    def draw(self, _area, ctx: cairo.Context, _width: int, _height: int) -> None:
        fill(ctx, 0, 0, WIDTH, HEIGHT, ZERO_PAPER)
        self.draw_panel(ctx)
        self.draw_bottom(ctx)

    def draw_panel(self, ctx: cairo.Context) -> None:
        state = self.window.state
        if state.mode == "result":
            fill(ctx, 0, 0, WIDTH, MAIN_H, PANEL_CREAM)
            fill(ctx, 0, 0, WIDTH, 18, TITLE_FILL)
            line(ctx, 0, 18, WIDTH, 18)
        else:
            fill(ctx, 5, 5, WIDTH - 10, MAIN_H - 9, HARD_SHADOW)
            fill(ctx, 4, 4, WIDTH - 10, MAIN_H - 9, PANEL_CREAM)
            stroke(ctx, 4, 4, WIDTH - 10, MAIN_H - 9)
            fill(ctx, 5, 5, WIDTH - 12, 18, TITLE_FILL)
            line(ctx, 4, 23, WIDTH - 7, 23)
        if state.mode == "result":
            text(ctx, "ROBOT", 8, 13, INK_BLACK, 8, True)
            self.draw_mode_badge(ctx, 58, 4, state.robot_mode, compact=True)
            text(ctx, fit_text(str(state.cwd), 27), 104, 13, MUTED_TEXT, 7)
            text(ctx, state.status, 260, 13, MUTED_TEXT, 7, True)
        else:
            text(ctx, "ROBOT", 11, 17, INK_BLACK, 10, True)
            self.draw_mode_badge(ctx, 64, 8, state.robot_mode)
            text(ctx, fit_text(str(state.cwd), 26), 111, 17, MUTED_TEXT, 8)
            text(ctx, state.status, 257, 17, ACCENT_ORANGE if state.mode == "running" else MUTED_TEXT, 8, True)

        if state.mode == "settings":
            self.draw_settings(ctx)
        elif state.mode == "edit_config":
            self.draw_edit_config(ctx)
        elif state.mode == "confirm_transcript":
            self.draw_transcript(ctx)
        elif state.mode == "running":
            self.draw_running(ctx)
        elif state.mode == "result":
            self.draw_result(ctx)
        elif state.mode == "error":
            self.draw_error(ctx)
        else:
            self.draw_compose(ctx)

    def draw_mode_badge(self, ctx: cairo.Context, x: int, y: int, value: RobotMode, compact: bool = False) -> None:
        w = 38 if compact else 39
        h = 10 if compact else 12
        fill(ctx, x, y, w, h, ICON_WELL)
        stroke(ctx, x, y, w, h, ACCENT_ORANGE if value != "SAFE" else LINE_BLACK)
        text(ctx, value, x + 5, y + (8 if compact else 9), ACCENT_ORANGE if value != "SAFE" else INK_BLACK, 6 if compact else 7, True)

    def draw_compose(self, ctx: cairo.Context) -> None:
        state = self.window.state
        text(ctx, "PROMPT", 12, 37, MUTED_TEXT, 8, True)
        fill(ctx, 11, 42, 298, 47, ICON_WELL)
        stroke(ctx, 11, 42, 298, 47, ACCENT_ORANGE)
        lines = wrap_text(state.prompt or "Type text, or press R to record voice.", 43, 4)
        for i, line_value in enumerate(lines):
            text(ctx, ("> " if i == 0 else "  ") + line_value, 17, 56 + i * 10, INK_BLACK if state.prompt else MUTED_TEXT, 8)
        if state.prompt:
            text(ctx, "_", 21 + min(len(state.prompt), 41) * 5, 56 + (len(lines) - 1) * 10, ACCENT_ORANGE, 8, True)

        tools = ",".join(MODE_TOOLS[state.robot_mode])
        text(ctx, "PI AGENT", 12, 103, MUTED_TEXT, 8, True)
        text(ctx, f"tools={fit_text(tools, 31)}", 13, 117, INK_BLACK, 8)
        model = str(self.window.config.get("model", "")).strip() or "default model"
        text(ctx, fit_text(model, 29), 13, 130, MUTED_TEXT, 8)
        text(ctx, "ENTER sends to pi rpc", 166, 130, MUTED_TEXT, 8)

    def draw_transcript(self, ctx: cairo.Context) -> None:
        state = self.window.state
        text(ctx, "TRANSCRIPT", 12, 39, MUTED_TEXT, 8, True)
        fill(ctx, 11, 45, 298, 65, ICON_WELL)
        stroke(ctx, 11, 45, 298, 65, ACCENT_ORANGE)
        for i, line_value in enumerate(wrap_text(state.transcript, 43, 5)):
            text(ctx, line_value, 17, 59 + i * 10, INK_BLACK, 8)
        text(ctx, "ENTER use transcript", 17, 128, OK_GREEN, 8, True)
        text(ctx, "C cancel", 190, 128, MUTED_TEXT, 8)

    def draw_running(self, ctx: cairo.Context) -> None:
        state = self.window.state
        elapsed = max(0, int(time.time() - state.started_at))
        text(ctx, f"RUNNING {elapsed}s", 12, 39, ACCENT_ORANGE, 8, True)
        fill(ctx, 11, 45, 298, 86, ICON_WELL)
        stroke(ctx, 11, 45, 298, 86)
        visible = state.events[-7:]
        for i, event in enumerate(visible):
            fg = WARN_RED if event.kind == "error" else MUTED_TEXT if event.kind in {"status", "note"} else INK_BLACK
            text(ctx, fit_text(event.text, 45), 17, 59 + i * 10, fg, 8)

    def draw_result(self, ctx: cairo.Context) -> None:
        state = self.window.state
        text(ctx, "CONVERSATION", 8, 29, OK_GREEN, 7, True)
        text(ctx, result_position(state.scroll, len(state.result_lines)), 263, 29, MUTED_TEXT, 7, True)
        line(ctx, 0, 33, WIDTH, 33, SOFT_LINE)
        lines = state.result_lines[state.scroll : state.scroll + RESULT_VISIBLE_LINES]
        for i, line_value in enumerate(lines):
            y = 42 + i * 7
            if line_value.startswith("YOU "):
                text(ctx, "YOU", 8, y, ACCENT_ORANGE, 6, True)
                text(ctx, fit_text(line_value[4:].strip(), RESULT_BODY_WIDTH), 28, y, INK_BLACK, 6)
            elif line_value.startswith("PI "):
                text(ctx, "PI", 8, y, OK_GREEN, 6, True)
                text(ctx, fit_text(line_value[3:].strip(), RESULT_BODY_WIDTH), 28, y, INK_BLACK, 6)
            elif not line_value:
                line(ctx, 8, y - 3, 312, y - 3, SOFT_LINE)
            else:
                text(ctx, fit_text(line_value, RESULT_LINE_WIDTH), 28, y, INK_BLACK, 6)

    def draw_error(self, ctx: cairo.Context) -> None:
        state = self.window.state
        text(ctx, "ERROR", 12, 39, WARN_RED, 8, True)
        fill(ctx, 11, 45, 298, 66, ICON_WELL)
        stroke(ctx, 11, 45, 298, 66, WARN_RED)
        for i, line_value in enumerate(wrap_text(state.error, 43, 5)):
            text(ctx, line_value, 17, 59 + i * 10, WARN_RED if i == 0 else INK_BLACK, 8)
        text(ctx, "C clears error", 17, 128, MUTED_TEXT, 8)

    def draw_settings(self, ctx: cairo.Context) -> None:
        state = self.window.state
        items = self.window.settings_items()
        text(ctx, "ROBOT SETTINGS", 12, 39, MUTED_TEXT, 8, True)
        start = max(0, min(state.settings_index - 3, max(0, len(items) - 5)))
        for row, item in enumerate(items[start : start + 5]):
            index = start + row
            y = 45 + row * 17
            selected = index == state.settings_index
            fill(ctx, 14, y, 292, 15, SELECT_FILL if selected else PANEL_CREAM)
            stroke(ctx, 14, y, 292, 15, ACCENT_ORANGE if selected else "#DCD5C3")
            text(ctx, item.label, 20, y + 11, ACCENT_ORANGE if selected else INK_BLACK, 8, True)
            text(ctx, fit_text(item.value, 23), 116, y + 11, MUTED_TEXT, 8)
            text(ctx, ">", 294, y + 11, MUTED_TEXT, 8, True)

    def draw_edit_config(self, ctx: cairo.Context) -> None:
        item = self.window.current_settings_item()
        label = item.label if item else self.window.state.edit_key.upper()
        text(ctx, fit_text(label, 28), 12, 39, MUTED_TEXT, 8, True)
        fill(ctx, 11, 45, 298, 48, ICON_WELL)
        stroke(ctx, 11, 45, 298, 48, ACCENT_ORANGE)
        for i, line_value in enumerate(wrap_text(self.window.state.edit_value or "Type value.", 43, 4)):
            text(ctx, ("> " if i == 0 else "  ") + line_value, 17, 59 + i * 10, INK_BLACK, 8)
        text(ctx, "ENTER save", 17, 119, OK_GREEN, 8, True)
        text(ctx, "C cancel", 122, 119, MUTED_TEXT, 8)
        if item and item.key == "cwd":
            text(ctx, "home or absolute path", 17, 133, MUTED_TEXT, 8)
        elif item and item.key == "pi_bin":
            text(ctx, "command name or path", 17, 133, MUTED_TEXT, 8)

    def draw_bottom(self, ctx: cairo.Context) -> None:
        y = MAIN_H
        fill(ctx, 0, y, WIDTH, BOTTOM_H, ZERO_PAPER)
        line(ctx, 0, y, WIDTH, y)
        state = self.window.state
        if state.mode == "running":
            draw_key(ctx, 8, y + 3, "C", 16)
            text(ctx, "CANCEL", 29, y + 13, INK_BLACK, 8, True)
            draw_key(ctx, 96, y + 3, "UP", 22)
            text(ctx, "LOG", 123, y + 13, MUTED_TEXT, 8)
            draw_key(ctx, 196, y + 3, "ENT", 28)
            text(ctx, "DETAIL", 229, y + 13, MUTED_TEXT, 8)
            return
        if state.mode in {"result", "error"}:
            draw_key(ctx, 8, y + 3, "B", 16)
            text(ctx, "BACK", 29, y + 13, INK_BLACK, 8, True)
            draw_key(ctx, 82, y + 3, "UP", 22)
            draw_key(ctx, 111, y + 3, "DN", 22)
            if state.mode == "result":
                text(ctx, result_position(state.scroll, len(state.result_lines)), 139, y + 13, MUTED_TEXT, 8, True)
            else:
                text(ctx, "SCROLL", 139, y + 13, MUTED_TEXT, 8)
            draw_key(ctx, 230, y + 3, "ENT", 28)
            text(ctx, "NEW", 263, y + 13, MUTED_TEXT, 8)
            return
        draw_key(ctx, 6, y + 3, "R", 16)
        text(ctx, "REC", 27, y + 13, INK_BLACK, 8, True)
        draw_key(ctx, 66, y + 3, "S", 16)
        text(ctx, "SET", 87, y + 13, INK_BLACK, 8, True)
        draw_key(ctx, 145, y + 3, "ENT", 28)
        text(ctx, "RUN", 178, y + 13, INK_BLACK, 8, True)
        draw_key(ctx, 238, y + 3, "C", 16)
        text(ctx, "CANCEL", 259, y + 13, MUTED_TEXT, 8)


class RobotWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Robot")
        self.config = load_config()
        mode = str(self.config.get("mode", "EDIT"))
        robot_mode: RobotMode = mode if mode in MODE_ORDER else "EDIT"  # type: ignore[assignment]
        self.state = RobotState(robot_mode=robot_mode, cwd=resolve_cwd(str(self.config.get("cwd", "home"))))
        self.agent = PiBackend(self.config)
        self.speech = SpeechBackend(self.config)
        self.event_queue: queue.Queue[AgentEvent] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.canvas = RobotCanvas(self)
        self.set_default_size(WIDTH, HEIGHT)
        self.set_size_request(WIDTH, HEIGHT)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_child(self.canvas)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self.on_key)
        self.add_controller(controller)
        GLib.timeout_add(120, self.drain_events)

    def settings_items(self) -> list["SettingsItem"]:
        mode_values = list(MODE_ORDER)
        return [
            SettingsItem("mode", "TOOLS", str(self.config.get("mode", "EDIT")), "choice", mode_values),
            SettingsItem("cwd", "CWD", str(self.config.get("cwd", "home")), "text"),
            SettingsItem("pi_bin", "PI BIN", str(self.config.get("pi_bin", "pi")), "text"),
            SettingsItem("provider", "PROVIDER", str(self.config.get("provider", "")) or "default", "text"),
            SettingsItem("model", "MODEL", str(self.config.get("model", "")) or "default", "text"),
            SettingsItem("session_dir", "SESSION", str(self.config.get("session_dir", "default")), "text"),
            SettingsItem("persist_session", "SESSION ON", "on" if self.config.get("persist_session", True) else "off", "toggle"),
            SettingsItem("offline", "OFFLINE", "on" if self.config.get("offline", False) else "off", "toggle"),
            SettingsItem("recorder", "RECORDER", str(self.config.get("recorder", "auto")), "choice", ["auto", "pw-record", "arecord"]),
            SettingsItem("record_seconds", "REC SECS", str(self.config.get("record_seconds", 5)), "choice", ["3", "5", "8", "10"]),
            SettingsItem(
                "transcribe_model",
                "STT MODEL",
                str(self.config.get("transcribe_model", "gpt-4o-mini-transcribe")),
                "choice",
                ["gpt-4o-mini-transcribe", "gpt-4o-transcribe"],
            ),
        ]

    def current_settings_item(self) -> "SettingsItem | None":
        items = self.settings_items()
        if not items:
            return None
        return items[min(self.state.settings_index, len(items) - 1)]

    def on_key(self, _controller, keyval: int, _keycode: int, state_flags: int) -> bool:
        ctrl = bool(state_flags & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
            return True

        if self.state.mode == "settings":
            return self.on_settings_key(keyval)
        if self.state.mode == "edit_config":
            return self.on_edit_config_key(keyval)
        if self.state.mode == "running":
            if keyval in (Gdk.KEY_c, Gdk.KEY_C):
                self.agent.cancel()
                self.set_error("agent cancelled")
                return True
            return False
        if self.state.mode in {"result", "error"}:
            return self.on_result_key(keyval)
        if self.state.mode == "confirm_transcript":
            return self.on_transcript_key(keyval)
        return self.on_compose_key(keyval)

    def on_compose_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.run_agent()
            return True
        if keyval in (Gdk.KEY_s, Gdk.KEY_S, Gdk.KEY_m, Gdk.KEY_M):
            self.state.mode = "settings"
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_r, Gdk.KEY_R):
            self.record_voice()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.state.prompt = ""
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Delete):
            self.state.prompt = self.state.prompt[:-1]
            self.canvas.queue_draw()
            return True
        if keyval == Gdk.KEY_space:
            self.state.prompt += " "
            self.canvas.queue_draw()
            return True
        char = Gdk.keyval_to_unicode(keyval)
        if char and char >= 32:
            self.state.prompt += chr(char)
            self.canvas.queue_draw()
            return True
        return False

    def on_transcript_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.state.prompt = self.state.transcript
            self.state.mode = "compose"
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C, Gdk.KEY_BackSpace, Gdk.KEY_Escape):
            self.state.mode = "compose"
            self.canvas.queue_draw()
            return True
        return False

    def on_settings_key(self, keyval: int) -> bool:
        items = self.settings_items()
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Left):
            self.state.settings_index = (self.state.settings_index - 1) % len(items)
        elif keyval in (Gdk.KEY_Down, Gdk.KEY_Right):
            self.state.settings_index = (self.state.settings_index + 1) % len(items)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activate_settings_item()
        elif keyval in (Gdk.KEY_c, Gdk.KEY_C, Gdk.KEY_b, Gdk.KEY_B, Gdk.KEY_BackSpace, Gdk.KEY_Escape):
            self.state.mode = "compose"
        else:
            return False
        self.canvas.queue_draw()
        return True

    def on_edit_config_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.save_edit_value()
            self.state.mode = "settings"
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C, Gdk.KEY_Escape):
            self.state.mode = "settings"
            self.canvas.queue_draw()
            return True
        if keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Delete):
            self.state.edit_value = self.state.edit_value[:-1]
            self.canvas.queue_draw()
            return True
        if keyval == Gdk.KEY_space:
            self.state.edit_value += " "
            self.canvas.queue_draw()
            return True
        char = Gdk.keyval_to_unicode(keyval)
        if char and char >= 32:
            self.state.edit_value += chr(char)
            self.canvas.queue_draw()
            return True
        return False

    def activate_settings_item(self) -> None:
        item = self.current_settings_item()
        if not item:
            return
        if item.kind == "choice" and item.choices:
            current = str(self.config.get(item.key, item.value))
            try:
                index = item.choices.index(current)
            except ValueError:
                index = -1
            self.update_config(item.key, item.choices[(index + 1) % len(item.choices)])
            return
        if item.kind == "toggle":
            self.update_config(item.key, not bool(self.config.get(item.key, False)))
            return
        self.state.edit_key = item.key
        self.state.edit_value = str(self.config.get(item.key, ""))
        self.state.mode = "edit_config"

    def save_edit_value(self) -> None:
        if not self.state.edit_key:
            return
        value: object = self.state.edit_value.strip()
        if self.state.edit_key == "record_seconds":
            try:
                value = max(1, int(str(value)))
            except ValueError:
                self.set_error("record seconds must be a number")
                return
        self.update_config(self.state.edit_key, value)

    def update_config(self, key: str, value: object) -> None:
        self.config[key] = value
        save_config(self.config)
        if key == "mode":
            mode = str(value)
            if mode in MODE_ORDER:
                self.state.robot_mode = mode  # type: ignore[assignment]
        elif key == "cwd":
            self.state.cwd = resolve_cwd(str(value))
        self.agent = PiBackend(self.config)
        self.speech = SpeechBackend(self.config)

    def on_result_key(self, keyval: int) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.state = RobotState(robot_mode=self.state.robot_mode, cwd=self.state.cwd)
        elif keyval in (Gdk.KEY_b, Gdk.KEY_B, Gdk.KEY_BackSpace, Gdk.KEY_Escape, Gdk.KEY_c, Gdk.KEY_C):
            self.state.mode = "compose"
        elif keyval == Gdk.KEY_Up:
            self.state.scroll = max(0, self.state.scroll - 1)
        elif keyval == Gdk.KEY_Down:
            self.state.scroll = min(max(0, len(self.state.result_lines) - RESULT_VISIBLE_LINES), self.state.scroll + 1)
        else:
            return False
        self.canvas.queue_draw()
        return True

    def record_voice(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.state.mode = "running"
        self.state.status = "REC"
        self.state.events = [AgentEvent("status", "recording voice")]
        self.state.started_at = time.time()
        self.canvas.queue_draw()

        def worker() -> None:
            ok, message = self.speech.record_and_transcribe()
            if ok:
                self.event_queue.put(AgentEvent("transcript", message))
            else:
                self.event_queue.put(AgentEvent("error", message))
            self.event_queue.put(AgentEvent("done", "speech"))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def run_agent(self) -> None:
        prompt = self.state.prompt.strip()
        if not prompt:
            self.set_error("prompt is empty")
            return
        if self.worker and self.worker.is_alive():
            return
        self.state.mode = "running"
        self.state.status = "RUN"
        self.state.started_at = time.time()
        self.state.events = [AgentEvent("prompt", prompt)]
        self.state.result_lines = []
        self.state.error = ""
        self.canvas.queue_draw()

        def worker() -> None:
            self.agent.run(prompt, self.state.cwd, self.state.robot_mode, self.event_queue)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def drain_events(self) -> bool:
        changed = False
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            changed = True
            if event.kind == "done":
                if event.text == "speech":
                    if self.state.mode != "error":
                        self.state.mode = "confirm_transcript"
                        self.state.status = "READY"
                elif self.state.mode != "error":
                    self.state.mode = "result"
                    self.state.status = "DONE"
                    self.state.result_lines = self.result_lines()
            elif event.kind == "transcript":
                self.state.transcript = event.text
                self.state.events.append(AgentEvent("transcript", event.text))
            elif event.kind == "final":
                self.state.last_message = event.text
                self.state.events.append(event)
            elif event.kind == "delta":
                self.state.last_message += event.text
                self.state.events.append(AgentEvent("final", self.state.last_message))
            elif event.kind == "error":
                self.set_error(event.text, queue_draw=False)
            else:
                self.state.events.append(event)
                if event.kind == "status":
                    self.state.status = fit_text(event.text.upper(), 6)
        if changed:
            self.canvas.queue_draw()
        return True

    def result_lines(self) -> list[str]:
        lines: list[str] = []
        prompt = clean_agent_text(self.state.prompt)
        if prompt:
            first = True
            for paragraph in prompt.splitlines():
                for line_value in wrap_text(paragraph, RESULT_BODY_WIDTH):
                    lines.append(("YOU " if first else "   ") + line_value)
                    first = False
            lines.append("")
        message = clean_agent_text(self.state.last_message)
        if message:
            first = True
            for paragraph in message.splitlines():
                for line_value in wrap_text(paragraph, RESULT_BODY_WIDTH):
                    lines.append(("PI " if first else "  ") + line_value)
                    first = False
            return lines[-120:] or ["PI Pi agent finished."]
        text_events = [
            clean_agent_text(event.text)
            for event in self.state.events
            if event.kind in {"final", "delta", "log", "note", "tool"} and event.text
        ]
        text_events = [event_text for event_text in text_events if event_text]
        if not text_events:
            lines.append("PI Pi agent finished.")
            return lines[-120:]
        first = True
        for event_text in text_events[-20:]:
            for paragraph in event_text.splitlines():
                for line_value in wrap_text(paragraph, RESULT_BODY_WIDTH):
                    lines.append(("PI " if first else "  ") + line_value)
                    first = False
        return lines[-120:] or ["PI Pi agent finished."]

    def set_error(self, message: str, queue_draw: bool = True) -> None:
        self.state.mode = "error"
        self.state.status = "ERROR"
        self.state.error = message
        if queue_draw:
            self.canvas.queue_draw()


class RobotApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.cardputerzero.defaultapps.robot")
        self.window: RobotWindow | None = None

    def do_activate(self) -> None:
        load_css()
        if self.window is None:
            self.window = RobotWindow(self)
        self.window.present()
        GLib.idle_add(self.window.canvas.grab_focus)


def run(argv: list[str] | None = None) -> int:
    app = RobotApplication()
    return app.run(argv or [])
