from __future__ import annotations

CSS = """
* {
  font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
  font-size: 10px;
  letter-spacing: 0;
}

window {
  background: #E9E4D5;
  color: #171717;
}

.zero-root {
  background: #E9E4D5;
  color: #171717;
  border: 1px solid #2A2A2A;
}

.zero-topbar,
.zero-bottombar {
  min-height: 20px;
  background: #F4F0E6;
  border-bottom: 1px solid #2A2A2A;
  padding: 0 6px;
}

.zero-bottombar {
  border-top: 1px solid #2A2A2A;
  border-bottom: 0;
}

.zero-title {
  font-weight: 700;
  font-size: 10px;
}

.zero-status {
  color: #6E6A61;
  font-size: 9px;
}

.zero-content {
  background: #E9E4D5;
  padding: 5px 6px;
}

.zero-card-grid {
  background: #E9E4D5;
}

.zero-card {
  min-height: 34px;
  padding: 4px 5px;
  background: #F4F0E6;
  color: #171717;
  border: 1px solid #2A2A2A;
  box-shadow: 2px 2px #C7BEAA;
}

.zero-card-active {
  background: #F8F4EA;
  border: 1px solid #171717;
  box-shadow: inset 0 -3px #E66A2C, 2px 2px #C7BEAA;
}

.zero-card-danger.zero-card-active {
  box-shadow: inset 0 -3px #B94A2C, 2px 2px #C7BEAA;
}

.zero-card-muted {
  color: #6E6A61;
}

.zero-card-title {
  font-size: 9px;
  font-weight: 700;
}

.zero-card-subtitle {
  font-size: 8px;
  color: #6E6A61;
}

.zero-badge {
  min-width: 20px;
  padding: 0 3px;
  background: #DCD5C3;
  color: #171717;
  border: 1px solid #2A2A2A;
  font-size: 8px;
}

.zero-meter {
  min-height: 8px;
  background: #DCD5C3;
  border: 1px solid #2A2A2A;
}

.zero-meter-fill {
  min-height: 6px;
  background: #E66A2C;
}

.zero-split-page {
  background: #E9E4D5;
}

.zero-rail {
  min-width: 96px;
  background: #F4F0E6;
  border: 1px solid #2A2A2A;
}

.zero-rail-row {
  min-height: 15px;
  padding: 1px 4px;
  border-bottom: 1px solid #DCD5C3;
  font-size: 8px;
  font-weight: 700;
}

.zero-rail-row-active {
  background: #F8F4EA;
  box-shadow: inset 3px 0 #E66A2C;
}

.zero-preview {
  background: #F4F0E6;
  border: 1px solid #2A2A2A;
  padding: 5px;
}

.zero-preview-title {
  font-size: 10px;
  font-weight: 700;
}

.zero-preview-line {
  font-size: 8px;
  color: #6E6A61;
}

.zero-hero {
  background: #F4F0E6;
  border: 1px solid #2A2A2A;
  padding: 5px;
  box-shadow: 2px 2px #C7BEAA;
}

.zero-hero-title {
  font-size: 11px;
  font-weight: 700;
}

.zero-hero-value {
  font-size: 13px;
  font-weight: 700;
}

.zero-chip-row {
  background: #E9E4D5;
}

.zero-chip {
  min-height: 20px;
  padding: 2px 4px;
  background: #DCD5C3;
  color: #171717;
  border: 1px solid #2A2A2A;
  font-size: 8px;
}

.zero-chip-active {
  background: #F8F4EA;
  box-shadow: inset 0 -3px #E66A2C;
}

.zero-row {
  min-height: 20px;
  padding: 0 4px;
  border: 1px solid transparent;
}

.zero-row:selected,
.zero-row-active {
  background: #F6F0DF;
  border: 1px solid #171717;
  box-shadow: inset 0 -3px #E66A2C;
}

.zero-row-title {
  font-size: 10px;
  font-weight: 700;
}

.zero-row-subtitle {
  font-size: 8px;
  color: #6E6A61;
}

.zero-muted {
  color: #6E6A61;
}

.zero-accent {
  color: #E66A2C;
}

.zero-warn {
  color: #B94A2C;
}

.zero-ok {
  color: #3A7D44;
}

button {
  min-height: 18px;
  padding: 0 6px;
  background: #DCD5C3;
  color: #171717;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
}

button:focus {
  outline: 1px solid #E66A2C;
  box-shadow: inset 0 -2px #E66A2C;
}

entry {
  min-height: 18px;
  padding: 0 4px;
  background: #F8F4EA;
  color: #171717;
  border: 1px solid #2A2A2A;
  border-radius: 3px;
}

entry:focus {
  border-color: #E66A2C;
}

.zero-dialog {
  background: #F4F0E6;
  border: 1px solid #2A2A2A;
  padding: 6px;
}
"""


def load_css() -> None:
    from czero_apps.ui.gtk import Gdk, Gtk

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
