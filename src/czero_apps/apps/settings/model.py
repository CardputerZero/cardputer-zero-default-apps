from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CategoryId = Literal["system", "display", "network", "sound", "power", "about"]
RowKind = Literal["value", "toggle", "slider", "action", "readonly"]


@dataclass(frozen=True)
class Category:
    id: CategoryId
    label: str
    icon: str


@dataclass(frozen=True)
class SettingRow:
    key: str
    label: str
    value: str
    kind: RowKind = "value"
    arrow: bool = False
    disabled: bool = False
    slider_value: int = 0
    toggle_on: bool = False
    action: str = ""


@dataclass(frozen=True)
class SettingsPage:
    category: CategoryId
    rows: tuple[SettingRow, ...]
    note: str = ""


@dataclass(frozen=True)
class SelectorOption:
    label: str
    value: str
    selected: bool = False


@dataclass(frozen=True)
class StackPage:
    title: str
    kind: str = "selector"
    rows: tuple[SettingRow, ...] = ()
    options: tuple[SelectorOption, ...] = ()
    confirm_action: str = ""
    message: str = ""
    field_key: str = ""
    text_value: str = ""
    password_target: str = ""
