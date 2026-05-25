# Specification

`cardputer-zero-default-apps` is a collection of ordinary Linux GUI
applications optimized for the Cardputer Zero internal screen.

## In Scope

- GTK4/Wayland small-screen UI.
- Settings, Terminal, Files, Power, System Monitor, and App Store entry points.
- Shared list/detail/dialog/status components.
- Command execution wrapper with timeout, stdout, stderr, and exit code.
- APPLaunch desktop entries and icons.
- Thin backends over existing Linux commands, procfs, sysfs, and user files.

## Out Of Scope

- Login or greeter.
- PAM.
- User creation.
- Session launch.
- DRM/KMS setup.
- labwc configuration.
- Seat assignment.
- Global Tab/Esc policy.
- Polkit agent.
- Privileged helper design.
- Package-manager implementation.

## Permission Rule

The apps do not decide authorization. They invoke normal Linux commands. If a
command needs privilege, the system's polkit policy and active polkit agent
decide whether to allow it.

## Display Rule

Every app must be a Wayland-capable GUI application and must declare:

```ini
X-Zero-Display=wayland
```

No app in this repository may own `/dev/fb*`, DRM devices, input devices, or
global keyboard shortcuts.

## Failure Rule

Missing optional commands are shown as unavailable. They must not crash the app.
