#!/usr/bin/env python3
"""Hypr theme engine — one palette drives Hyprland, Waybar, kitty, hyprlock, dunst and hyprpaper."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from string import Template

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
HYPR = CONFIG / "hypr"
WAYBAR = CONFIG / "waybar"
KITTY = CONFIG / "kitty"
DUNST = CONFIG / "dunst"
THEMES_DIR = HYPR / "themes"
TEMPLATES_DIR = HYPR / "templates"
SCRIPTS_DIR = HYPR / "scripts"
STATE_PATH = HYPR / "theme-state.json"
WALLPAPER_DIR = HOME / "Pictures" / "Wallpapers"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "hypr-theme"

FONT = "JetBrainsMono Nerd Font"
THEME_ORDER = [
    "ascent",
    "ascent-dawn",
    "catppuccin-mocha",
    "gruvbox-dark",
    "nord",
    "rose-pine",
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".jxl"}
FIT_MODES = {"cover", "contain", "fill", "tile"}

DEFAULT_STATE = {
    "theme": "ascent",
    "wallpaper": str(WALLPAPER_DIR / "hyprland-0.png"),
    "wallpaper_render": str(WALLPAPER_DIR / "hyprland-0.png"),
    "fit_mode": "cover",
    "waybar_layout": "default",
    "bar_position": "top",
    "blur": False,
    "animations": True,
    "shadow": True,
    "rounding": 8,
    "gaps_in": 2,
    "gaps_out": 5,
    "border_size": 2,
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def run(cmd: list[str], *, timeout: float = 10, capture: bool = True):
    try:
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            env=env_with_path(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def env_with_path() -> dict[str, str]:
    env = os.environ.copy()
    local_bin = str(HOME / ".local" / "bin")
    env["PATH"] = local_bin + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    return env


def hyprland_running() -> bool:
    return run(["hyprctl", "version"], timeout=3).returncode == 0


def hyprctl(*args: str, timeout: float = 5):
    return run(["hyprctl", *args], timeout=timeout)


def _hex(color: str) -> str:
    return color.strip().lstrip("#").lower()


def rgba(color: str, alpha: str = "ff") -> str:
    return f"rgba({_hex(color)}{alpha})"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def expand_path(path: str | Path) -> Path:
    """Expand ~, $VARS and resolve a path from the theme state."""
    return Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()


def portable_path(path: str | Path) -> str:
    """Store paths under $HOME with a leading ~ so the dotfiles clone well."""
    resolved = Path(path).resolve()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except OSError:
            pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


# --------------------------------------------------------------------------- #
# themes + state
# --------------------------------------------------------------------------- #
def theme_slugs() -> list[str]:
    found = {p.stem for p in THEMES_DIR.glob("*.toml")}
    ordered = [s for s in THEME_ORDER if s in found]
    return ordered + sorted(found - set(ordered))


def load_theme(slug: str | None = None) -> dict:
    slug = slug or current_theme_slug()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug or ""):
        raise ValueError(f"invalid theme name: {slug!r}")
    path = THEMES_DIR / f"{slug}.toml"
    if not path.exists():
        raise FileNotFoundError(f"theme not found: {slug}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    data["slug"] = slug
    data.setdefault("name", slug)
    data.setdefault("description", "")
    data.setdefault("variant", "dark")
    data.setdefault("accent_name", "")
    colors = data.setdefault("colors", {})
    required = [
        "bg", "bg_alt", "surface", "surface_alt", "fg", "fg_dim", "muted",
        "border", "accent", "accent_alt", "gold", "red", "green", "blue",
        "magenta", "cyan", "orange", "on_accent", "on_bg", "shadow",
    ]
    missing = [key for key in required if key not in colors]
    if missing:
        raise ValueError(f"{slug}: missing colors: {', '.join(missing)}")
    data.setdefault("terminal", {})
    return data


def load_state() -> dict:
    state = dict(DEFAULT_STATE)
    if STATE_PATH.exists():
        try:
            state.update(json.loads(STATE_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    if not (THEMES_DIR / f"{state.get('theme', '')}.toml").exists():
        state["theme"] = "ascent"
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def current_theme_slug() -> str:
    return load_state()["theme"]


def theme_summary(slug: str) -> dict:
    theme = load_theme(slug)
    return {
        "slug": slug,
        "name": theme["name"],
        "description": theme["description"],
        "variant": theme["variant"],
        "accent_name": theme["accent_name"],
        "colors": theme["colors"],
    }


def all_themes() -> list[dict]:
    return [theme_summary(slug) for slug in theme_slugs()]


# --------------------------------------------------------------------------- #
# renderers
# --------------------------------------------------------------------------- #
def render_lua(theme: dict, state: dict) -> str:
    c = theme["colors"]
    active = rgba(c["accent"], "ee")
    inactive = rgba(c["border"], "88")
    shadow = "0xee" + _hex(c["shadow"])
    blur = "true" if state["blur"] else "false"
    animations = "true" if state["animations"] else "false"
    shadow_enabled = "true" if state["shadow"] else "false"
    return f"""-- Generated by ~/.config/hypr/scripts/theme-switch — do not edit.
-- Palette source: hypr/themes/{theme['slug']}.toml
hl.config({{
    general = {{
        gaps_in = {int(state['gaps_in'])},
        gaps_out = {int(state['gaps_out'])},
        border_size = {int(state['border_size'])},
        col = {{
            active_border = "{active}",
            inactive_border = "{inactive}",
        }},
    }},
    decoration = {{
        rounding = {int(state['rounding'])},
        active_opacity = 1.0,
        inactive_opacity = 1.0,
        shadow = {{
            enabled = {shadow_enabled},
            range = 12,
            render_power = 3,
            color = "{shadow}",
        }},
        blur = {{
            enabled = {blur},
            size = 6,
            passes = 2,
            vibrancy = 0.1696,
        }},
    }},
    animations = {{
        enabled = {animations},
    }},
}})

return {{
    name = "{theme['name']}",
    slug = "{theme['slug']}",
    variant = "{theme['variant']}",
}}
"""


def render_kitty(theme: dict) -> str:
    c = theme["colors"]
    term = theme.get("terminal", {})
    lines = [
        f"# Generated from hypr/themes/{theme['slug']}.toml — do not edit.",
        f"# {theme['name']} by the Hypr theme engine.",
        "",
        f"foreground            {c['fg']}",
        f"background            {c['bg']}",
        f"selection_foreground   {c['bg']}",
        f"selection_background   {c['accent']}",
        f"cursor                {c['accent']}",
        f"cursor_text_color      {c['bg']}",
        f"url_color             {c['cyan']}",
        f"active_border_color    {c['accent']}",
        f"inactive_border_color  {c['border']}",
        f"active_tab_background  {c['accent']}",
        f"active_tab_foreground  {c['on_accent']}",
        f"inactive_tab_background {c['surface']}",
        f"inactive_tab_foreground {c['fg_dim']}",
        f"tab_bar_background     {c['bg_alt']}",
        "",
    ]
    for index in range(16):
        color = term.get(str(index)) or term.get(index)
        if color:
            lines.append(f"color{index:<14}{color}")
    return "\n".join(lines) + "\n"


def render_waybar(theme: dict) -> str:
    c = theme["colors"]
    keys = [
        "bg", "bg_alt", "surface", "surface_alt", "fg", "fg_dim", "muted",
        "border", "accent", "accent_alt", "gold", "red", "green", "blue",
        "magenta", "cyan", "orange", "on_accent", "on_bg", "shadow",
    ]
    lines = [
        f"/* Generated from hypr/themes/{theme['slug']}.toml — do not edit. */",
        f"/* {theme['name']} */",
        "",
    ]
    for key in keys:
        lines.append(f"@define-color {key:<12} {c[key]};")
    lines += [
        "",
        "/* aliases used by older module rules */",
        "@define-color window_bg @bg;",
        "@define-color window_fg @fg;",
    ]
    return "\n".join(lines) + "\n"


def _template(name: str) -> Template:
    path = TEMPLATES_DIR / name
    return Template(path.read_text(encoding="utf-8"))


def _template_values(theme: dict, state: dict) -> dict[str, str]:
    c = theme["colors"]
    raw_wallpaper = state.get("wallpaper_render") or state.get("wallpaper")
    wallpaper = str(expand_path(raw_wallpaper)) if raw_wallpaper else str(WALLPAPER_DIR / "hyprland-0.png")
    if not Path(wallpaper).exists():
        wallpaper = str(WALLPAPER_DIR / "hyprland-0.png")
    if not Path(wallpaper).exists():
        wallpaper = "screenshot"
    fit = state.get("fit_mode", "cover")
    if fit not in FIT_MODES:
        fit = "cover"
    is_dir = Path(wallpaper).is_dir()
    values = {
        "theme_slug": theme["slug"],
        "theme_name": theme["name"],
        "font": FONT,
        "wallpaper": wallpaper,
        "fit_mode": fit,
        "timeout": "300" if is_dir else "30",
        "blur_passes": "3" if state.get("blur") else "1",
        "rounding": str(int(state["rounding"])),
        "surface_alpha": rgba(c["surface"], "e6"),
        "bg_alpha": rgba(c["bg"], "e6"),
    }
    for key, value in c.items():
        values[key] = value
    return values


def render_hyprlock(theme: dict, state: dict) -> str:
    values = _template_values(theme, state)
    for key, value in theme["colors"].items():
        values[key] = rgba(value)
    values["muted_hex"] = theme["colors"]["muted"]
    return _template("hyprlock.conf.in").safe_substitute(values)


def render_dunst(theme: dict, state: dict) -> str:
    return _template("dunstrc.in").safe_substitute(_template_values(theme, state))


def render_hyprpaper(theme: dict, state: dict) -> str:
    return _template("hyprpaper.conf.in").safe_substitute(_template_values(theme, state))


def render_all(theme: dict | None = None, state: dict | None = None) -> list[Path]:
    state = state or load_state()
    theme = theme or load_theme(state["theme"])
    written: list[Path] = []
    targets = [
        (HYPR / "theme.lua", render_lua(theme, state)),
        (KITTY / "theme.conf", render_kitty(theme)),
        (WAYBAR / "colors.css", render_waybar(theme)),
        (HYPR / "hyprlock.conf", render_hyprlock(theme, state)),
        (HYPR / "hyprpaper.conf", render_hyprpaper(theme, state)),
        (DUNST / "dunstrc", render_dunst(theme, state)),
    ]
    for path, text in targets:
        if write_if_changed(path, text):
            written.append(path)
    return written


# --------------------------------------------------------------------------- #
# reloads
# --------------------------------------------------------------------------- #
def reload_hyprland() -> None:
    if hyprland_running():
        hyprctl("reload")


def reload_waybar_style() -> None:
    if run(["pgrep", "-x", "waybar"]).returncode == 0:
        run(["pkill", "-USR2", "-x", "waybar"])


def reload_kitty() -> None:
    if run(["pgrep", "-x", "kitty"]).returncode == 0:
        run(["pkill", "-USR1", "-x", "kitty"])


def reload_dunst() -> None:
    if run(["pgrep", "-x", "dunst"]).returncode == 0:
        run(["dunstctl", "reload"], timeout=3)


def restart_waybar() -> bool:
    run(["pkill", "-x", "waybar"])
    time.sleep(0.35)
    subprocess.Popen(
        ["waybar"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env_with_path(),
    )
    for _ in range(30):
        time.sleep(0.1)
        if run(["pgrep", "-x", "waybar"]).returncode == 0:
            return True
    return False


# --------------------------------------------------------------------------- #
# wallpapers
# --------------------------------------------------------------------------- #
def hyprpaper_binary() -> str | None:
    local = HOME / ".local" / "bin" / "hyprpaper"
    if local.exists():
        return str(local)
    return shutil.which("hyprpaper")


def hyprpaper_running() -> bool:
    return run(["pgrep", "-x", "hyprpaper"]).returncode == 0


def hyprpaper_ipc_ok() -> bool:
    return run(["hyprctl", "hyprpaper", "listactive"], timeout=3).returncode == 0


def start_hyprpaper() -> bool:
    binary = hyprpaper_binary()
    if not binary:
        return False
    subprocess.Popen(
        [binary],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env_with_path(),
    )
    for _ in range(30):
        time.sleep(0.1)
        if hyprpaper_ipc_ok():
            return True
    return False


def stop_hyprpaper() -> None:
    run(["pkill", "-x", "hyprpaper"])
    for _ in range(20):
        if not hyprpaper_running():
            return
        time.sleep(0.1)


def monitor_names() -> list[str]:
    result = hyprctl("monitors", "-j")
    if result.returncode == 0:
        try:
            return [m["name"] for m in json.loads(result.stdout) if m.get("name")]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return []


def list_wallpapers(directory: Path | None = None) -> list[Path]:
    directory = directory or WALLPAPER_DIR
    if not directory.exists():
        return []
    files = [
        p for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=lambda p: (p.parent.name.lower(), p.name.lower()))


def _png_for_hyprpaper(path: Path) -> Path:
    """hyprpaper 0.8.4 in Debian crashes on JPEG IPC; feed it a cached PNG."""
    if path.suffix.lower() == ".png":
        return path
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stat = path.stat()
    key = f"{path.stem}-{stat.st_size}-{int(stat.st_mtime)}".replace(" ", "_")
    target = CACHE_DIR / f"{key}.png"
    if target.exists():
        return target
    result = run(
        ["magick", str(path), "-strip", "-resize", "2560x1600>", str(target)],
        timeout=90,
    )
    if result.returncode != 0 or not target.exists():
        return path
    return target


def _apply_wallpaper_ipc(path: Path, fit: str) -> bool:
    monitors = monitor_names() or [""]
    ok = False
    for monitor in monitors:
        arg = f"{monitor},{path},{fit}"
        result = run(["hyprctl", "hyprpaper", "wallpaper", arg], timeout=10)
        ok = ok or result.returncode == 0
    return ok


def set_wallpaper(path: str | Path, fit: str | None = None) -> dict:
    state = load_state()
    source = expand_path(path)
    if not source.exists():
        raise FileNotFoundError(f"wallpaper not found: {source}")
    fit = fit or state.get("fit_mode", "cover")
    if fit not in FIT_MODES:
        raise ValueError(f"unsupported fit mode: {fit}")

    directory_mode = source.is_dir()
    if directory_mode:
        render = source
    else:
        if source.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"unsupported image: {source.suffix}")
        render = _png_for_hyprpaper(source)

    state["wallpaper"] = portable_path(source)
    state["wallpaper_render"] = portable_path(render)
    state["fit_mode"] = fit
    save_state(state)

    theme = load_theme(state["theme"])
    render_all(theme, state)

    # hyprpaper 0.8.4 segfaults when a config with a wallpaper block receives a
    # runtime `wallpaper` IPC command. Restarting it with the generated config is
    # both reliable and what makes directory slideshows work.
    stop_hyprpaper()
    started = start_hyprpaper()
    applied = bool(started and hyprpaper_ipc_ok())

    state["wallpaper_applied"] = applied
    save_state(state)
    return state


def random_wallpaper() -> Path:
    files = list_wallpapers()
    if not files:
        raise FileNotFoundError(f"no wallpapers in {WALLPAPER_DIR}")
    import random
    return random.SystemRandom().choice(files)


# --------------------------------------------------------------------------- #
# waybar layouts
# --------------------------------------------------------------------------- #
def waybar_presets() -> list[str]:
    return sorted(
        p.stem for p in (WAYBAR / "presets").glob("*.json")
        if not p.stem.startswith("_")
    )


def _waybar_preset_path(layout: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", layout or ""):
        raise ValueError(f"invalid layout: {layout!r}")
    path = WAYBAR / "presets" / f"{layout}.json"
    if not path.exists():
        raise FileNotFoundError(f"waybar preset not found: {layout}")
    return path


def apply_waybar(layout: str | None = None, position: str | None = None) -> dict:
    state = load_state()
    layout = layout or state.get("waybar_layout", "default")
    position = position or state.get("bar_position", "top")
    if position not in {"top", "bottom", "left", "right"}:
        raise ValueError(f"invalid bar position: {position}")
    config: dict = {}
    shared = WAYBAR / "presets" / "_modules.json"
    if shared.exists():
        config.update(json.loads(shared.read_text(encoding="utf-8")))
    config.update(json.loads(_waybar_preset_path(layout).read_text(encoding="utf-8")))
    config["position"] = position
    if position in {"left", "right"}:
        config["width"] = 72
        # Vertical bars need icon-first formats or text spills out of the pill.
        for module, values in {
            "network": {"format": "{icon}", "format-wifi": "{icon}",
                        "format-ethernet": "󰈀", "format-disconnected": "󰤮"},
            "mpris": {"format": "{status_icon}"},
            "clock": {"format": "{:%H:%M}"},
            "cpu": {"format": "{usage}%"},
            "memory": {"format": "{percentage}%"},
            "battery": {"format": "{icon}", "format-charging": "󰂄",
                        "format-plugged": "󰂅"},
            "custom/updates": {"format": "󰏖 {}"},
        }.items():
            if module in config:
                config[module].update(values)
    else:
        config.setdefault("width", 620)
    (WAYBAR / "config.jsonc").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    state["waybar_layout"] = layout
    state["bar_position"] = position
    save_state(state)
    restart_waybar()
    return state


# --------------------------------------------------------------------------- #
# public operations
# --------------------------------------------------------------------------- #
def apply_theme(slug: str | None = None, *, reload: bool = True) -> dict:
    state = load_state()
    if slug:
        load_theme(slug)  # validates
        state["theme"] = slug
        save_state(state)
    theme = load_theme(state["theme"])
    render_all(theme, state)
    if reload:
        reload_hyprland()
        reload_waybar_style()
        reload_kitty()
        reload_dunst()
    return state


def next_theme(direction: int = 1) -> str:
    state = load_state()
    slugs = theme_slugs()
    try:
        index = slugs.index(state["theme"])
    except ValueError:
        index = 0
    slug = slugs[(index + direction) % len(slugs)]
    apply_theme(slug)
    return slug


def set_option(key: str, value) -> dict:
    state = load_state()
    bool_keys = {"blur", "animations", "shadow"}
    int_keys = {"rounding", "gaps_in", "gaps_out", "border_size"}
    if key in bool_keys:
        state[key] = _as_bool(value)
    elif key in int_keys:
        state[key] = max(0, int(value))
    else:
        raise ValueError(f"unknown option: {key}")
    save_state(state)
    theme = load_theme(state["theme"])
    render_all(theme, state)
    reload_hyprland()
    return state


def status() -> dict:
    state = load_state()
    theme = load_theme(state["theme"])
    return {
        "theme": theme["slug"],
        "theme_name": theme["name"],
        "variant": theme["variant"],
        "wallpaper": state.get("wallpaper"),
        "fit_mode": state.get("fit_mode"),
        "waybar_layout": state.get("waybar_layout"),
        "bar_position": state.get("bar_position"),
        "blur": state.get("blur"),
        "animations": state.get("animations"),
        "shadow": state.get("shadow"),
        "hyprpaper_running": hyprpaper_running(),
        "hyprpaper_binary": hyprpaper_binary(),
        "waybar_running": run(["pgrep", "-x", "waybar"]).returncode == 0,
        "hyprland_running": hyprland_running(),
        "monitors": monitor_names(),
        "wallpaper_dir": str(WALLPAPER_DIR),
        "themes": theme_slugs(),
        "layouts": waybar_presets(),
    }


def ensure_dirs() -> None:
    for path in (HYPR, WAYBAR, KITTY, DUNST, THEMES_DIR, TEMPLATES_DIR, WALLPAPER_DIR, CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
