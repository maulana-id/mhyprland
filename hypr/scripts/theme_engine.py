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
    # cava visualizer settings
    "cava_freq_low": 20,
    "cava_freq_high": 1000,
    "cava_bars": 6,
    "cava_noise": 77,
    "cava_sensitivity": 100,
    "cava_enabled": True,
    "cava_channels": "mono",
    "cava_mirror": True,
    "cava_direction": "middle-out",
    "cava_group_mode": "gradient",
    "cava_group_gap": True,
    "cava_bass_punch": True,
    "cava_color_1": "accent",
    "cava_color_2": "gold",
    "cava_color_3": "cyan",
    "cava_color_4": "red",
    "cava_color_mode": "gradient",
    "cava_grad_from": "accent",
    "cava_grad_to": "gold",
    "cava_framerate": 24,
    "cava_silence": 32,
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


def render_hyprtoolkit(theme: dict, state: dict) -> str:
    c = theme["colors"]

    def argb(color: str) -> str:
        return "0xFF" + _hex(color).upper()

    return f"""# Generated from hypr/themes/{theme['slug']}.toml — do not edit.
# Hyprlauncher, hyprshutdown and other Hyprtoolkit apps read this palette.
background = {argb(c['bg'])}
base = {argb(c['surface'])}
text = {argb(c['fg'])}
alternate_base = {argb(c['surface_alt'])}
bright_text = {argb(c['on_bg'])}
link_text = {argb(c['cyan'])}
accent = {argb(c['accent'])}
accent_secondary = {argb(c['accent_alt'])}
rounding_large = 12
rounding_small = 6
h1_size = 19
h2_size = 15
h3_size = 13
font_size = 11
small_font_size = 10
icon_theme =
font_family = Noto Sans
font_family_monospace = JetBrainsMono Nerd Font
"""


def render_hyprlock(theme: dict, state: dict) -> str:
    values = _template_values(theme, state)
    for key, value in theme["colors"].items():
        values[key] = rgba(value)
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
        (HYPR / "hyprtoolkit.conf", render_hyprtoolkit(theme, state)),
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
    launcher = WAYBAR / "scripts" / "start-waybar"
    command = [str(launcher)] if launcher.exists() else ["waybar"]
    subprocess.Popen(
        command,
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
    if not state.get("cava_enabled", True):
        for key in ("modules-left", "modules-center", "modules-right"):
            config[key] = [m for m in config.get(key, []) if m != "custom/cava"]
    if position in {"left", "right"}:
        config["width"] = 72
        # Vertical bars need icon-first formats or text spills out of the pill.
        for module, values in {
            "network": {"format": "{icon}", "format-wifi": "{icon}",
                        "format-ethernet": "󰈀", "format-disconnected": "󰤮"},
            "mpris": {"format": "{status_icon}"},
            "clock": {"format": "{:%H:%M}"},
            "custom/resources": {"format": "󰍛"},
            "battery": {"format": "{icon}", "format-charging": "󰂄",
                        "format-plugged": "󰂅"},
        }.items():
            if module in config:
                config[module].update(values)
        # A horizontal spectrum does not fit a 72px column.
        for key in ("modules-left", "modules-center", "modules-right"):
            config[key] = [m for m in config.get(key, []) if m != "custom/cava"]
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


_COLOR_CHOICES = {"accent", "accent_alt", "gold", "cyan", "green", "red", "blue", "magenta", "orange", "fg"}

_CAVA_INT_RANGES: dict[str, tuple[int, int]] = {
    "cava_freq_low": (1, 1000),
    "cava_freq_high": (100, 22000),
    "cava_bars": (2, 32),
    "cava_noise": (0, 100),
    "cava_sensitivity": (50, 300),
    "cava_framerate": (12, 60),
    "cava_silence": (0, 120),
}
_CAVA_BOOL_KEYS = {"cava_enabled", "cava_mirror", "cava_group_gap", "cava_bass_punch"}
_CAVA_STRING_OPTIONS: dict[str, set[str]] = {
    "cava_channels": {"mono", "stereo"},
    "cava_direction": {"middle-out", "edges-in", "left-to-right", "right-to-left"},
    "cava_group_mode": {"1", "2", "3", "4", "gradient"},
    "cava_color_1": _COLOR_CHOICES,
    "cava_color_2": _COLOR_CHOICES,
    "cava_color_3": _COLOR_CHOICES,
    "cava_color_4": _COLOR_CHOICES,
    "cava_color_mode": {"gradient", "theme", "solid"},
    "cava_grad_from": _COLOR_CHOICES,
    "cava_grad_to": _COLOR_CHOICES,
}


CAVA_BLOCKS = "▁▂▃▄▅▆▇█"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lerp_color(color_a: str, color_b: str, t: float) -> str:
    """Linear interpolate between two hex colors; t=0 -> a, t=1 -> b."""
    ar, ag, ab = hex_to_rgb(color_a)
    br, bg, bb = hex_to_rgb(color_b)
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    b = int(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def render_cava(values: list[int], colors: dict, cava_state: dict) -> str:
    """
    Render bars as Pango markup according to user customization:
    - direction: "middle-out" (centered mirror), "edges-in" (outside-in mirror),
                 "left-to-right" (bass left), "right-to-left" (treble left)
    - group_mode: "1" (solid), "2" (bi-band), "3" (tri-band), "4" (quad-band), "gradient" (smooth lerp)
    - group_gap: bool (whether to insert separation space between groups)
    - bass_punch: bool (whether to give low-end an extra kick)
    - color_1 .. color_4: theme palette keys
    """
    n = len(values)
    if n == 0:
        return ""

    direction: str = str(cava_state.get("direction", ""))
    if not direction:
        direction = "middle-out" if cava_state.get("mirror", True) else "left-to-right"

    group_mode: str = str(cava_state.get("group_mode", ""))
    if not group_mode:
        cm = str(cava_state.get("color_mode", "gradient"))
        group_mode = "gradient" if cm == "gradient" else ("1" if cm == "solid" else "3")

    group_gap: bool = bool(cava_state.get("group_gap", True))
    bass_punch: bool = bool(cava_state.get("bass_punch", True))

    c1_name = cava_state.get("color_1", cava_state.get("gradient_from", "accent"))
    c2_name = cava_state.get("color_2", cava_state.get("gradient_to", "gold"))
    c3_name = cava_state.get("color_3", "cyan")
    c4_name = cava_state.get("color_4", "red")

    c1 = colors.get(c1_name, "#7aa2f7")
    c2 = colors.get(c2_name, "#e0af68")
    c3 = colors.get(c3_name, "#7dcfff")
    c4 = colors.get(c4_name, "#f7768e")

    # Low-end boost
    processed = list(values)
    if bass_punch:
        punch_count = max(1, n // 4)
        for i in range(min(punch_count, n)):
            if processed[i] > 0:
                processed[i] = min(7, processed[i] + 1)

    sep = "\u2009"  # thin space within a group
    gap = " "       # space between groups

    def _group_index(index: int, total: int, count: int) -> int:
        quotient, remainder = divmod(total, count)
        larger_groups_end = (quotient + 1) * remainder
        if index < larger_groups_end:
            return index // (quotient + 1)
        return remainder + (index - larger_groups_end) // quotient

    def _render_grouped(items: list[tuple[int, int]]) -> str:
        count = min(4, n, max(1, int(group_mode)))
        parts: list[str] = []
        previous_group: int | None = None
        for value, frequency_index in items:
            group_index = _group_index(frequency_index, n, count)
            color = [c1, c2, c3, c4][group_index]
            if parts:
                parts.append(gap if group_gap and group_index != previous_group else sep)
            parts.append(f'<span foreground="{color}">{CAVA_BLOCKS[value]}</span>')
            previous_group = group_index
        return "".join(parts)

    if direction in ("middle-out", "edges-in"):
        if direction == "middle-out":
            left_half_vals = list(reversed(processed))  # treble -> bass
            right_half_vals = list(processed)           # bass -> treble
        else:
            left_half_vals = list(processed)           # bass -> treble
            right_half_vals = list(reversed(processed)) # treble -> bass

        if group_mode == "gradient":
            def _grad_col(pos: int, total_half: int) -> str:
                t = pos / max(total_half - 1, 1)
                return lerp_color(c1, c2, t)

            left_spans = [
                f'<span foreground="{_grad_col(i, n)}">{CAVA_BLOCKS[v]}</span>'
                for i, v in enumerate(left_half_vals)
            ]
            right_spans = [
                f'<span foreground="{_grad_col(n - 1 - i, n)}">{CAVA_BLOCKS[v]}</span>'
                for i, v in enumerate(right_half_vals)
            ]
            return f"{sep.join(left_spans)}{gap}{sep.join(right_spans)}"

        else:
            left_indices = range(n - 1, -1, -1) if direction == "middle-out" else range(n)
            right_indices = range(n) if direction == "middle-out" else range(n - 1, -1, -1)
            left_rendered = _render_grouped(list(zip(left_half_vals, left_indices)))
            right_rendered = _render_grouped(list(zip(right_half_vals, right_indices)))
            return f"{left_rendered}{gap}{right_rendered}"

    else:
        # Linear layouts: "left-to-right" or "right-to-left"
        linear_vals = list(processed) if direction == "left-to-right" else list(reversed(processed))

        if group_mode == "gradient":
            spans = []
            for i, v in enumerate(linear_vals):
                t = i / max(n - 1, 1)
                color = lerp_color(c1, c2, t)
                spans.append(f'<span foreground="{color}">{CAVA_BLOCKS[v]}</span>')
            return sep.join(spans)

        else:
            frequency_indices = range(n) if direction == "left-to-right" else range(n - 1, -1, -1)
            return _render_grouped(list(zip(linear_vals, frequency_indices)))


def _write_cava_state_json(state: dict) -> None:
    """Sync relevant cava_* keys from theme state into waybar/cava-state.json."""
    direction = str(state.get("cava_direction", ""))
    if not direction:
        direction = "middle-out" if state.get("cava_mirror", True) else "left-to-right"
    if not bool(state.get("cava_mirror", True)) and direction in ("middle-out", "edges-in"):
        direction = "left-to-right"

    group_mode = str(state.get("cava_group_mode", ""))
    if not group_mode:
        cm = str(state.get("cava_color_mode", "gradient"))
        group_mode = "gradient" if cm == "gradient" else ("1" if cm == "solid" else "3")

    cava_state = {
        "enabled": bool(state.get("cava_enabled", True)),
        "freq_low": int(state.get("cava_freq_low", 20)),
        "freq_high": int(state.get("cava_freq_high", 1000)),
        "bars": int(state.get("cava_bars", 6)),
        "noise_reduction": round(int(state.get("cava_noise", 77)) / 100.0, 2),
        "sensitivity": int(state.get("cava_sensitivity", 100)),
        "channels": str(state.get("cava_channels", "mono")),
        "direction": direction,
        "mirror": direction in ("middle-out", "edges-in"),
        "group_mode": group_mode,
        "group_gap": bool(state.get("cava_group_gap", True)),
        "bass_punch": bool(state.get("cava_bass_punch", True)),
        "color_1": str(state.get("cava_color_1", state.get("cava_grad_from", "accent"))),
        "color_2": str(state.get("cava_color_2", state.get("cava_grad_to", "gold"))),
        "color_3": str(state.get("cava_color_3", "cyan")),
        "color_4": str(state.get("cava_color_4", "red")),
        "color_mode": str(state.get("cava_color_mode", "gradient")),
        "gradient_from": str(state.get("cava_grad_from", state.get("cava_color_1", "accent"))),
        "gradient_to": str(state.get("cava_grad_to", state.get("cava_color_2", "gold"))),
        "framerate": int(state.get("cava_framerate", 24)),
        "silence_timeout": int(state.get("cava_silence", 32)),
        "bar_style": "blocks",
    }
    cava_state_path = WAYBAR / "cava-state.json"
    cava_state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cava_state_path.with_name(cava_state_path.name + ".tmp")
    tmp.write_text(json.dumps(cava_state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(cava_state_path)


def _signal_cava_waybar() -> None:
    """Send SIGUSR1 to any running cava-waybar process to trigger a restart."""
    try:
        subprocess.run(
            ["pkill", "-USR1", "-f", "cava-waybar"],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def set_option(key: str, value) -> dict:
    state = load_state()
    bool_keys = {"blur", "animations", "shadow"}
    int_keys = {"rounding", "gaps_in", "gaps_out", "border_size"}
    is_cava = (
        key in _CAVA_INT_RANGES
        or key in _CAVA_BOOL_KEYS
        or key in _CAVA_STRING_OPTIONS
    )
    if key in bool_keys or key in _CAVA_BOOL_KEYS:
        state[key] = _as_bool(value)
    elif key in int_keys:
        state[key] = max(0, int(value))
    elif key in _CAVA_INT_RANGES:
        lo, hi = _CAVA_INT_RANGES[key]
        state[key] = max(lo, min(hi, int(value)))
    elif key in _CAVA_STRING_OPTIONS:
        allowed = _CAVA_STRING_OPTIONS[key]
        sv = str(value)
        if sv not in allowed:
            raise ValueError(f"{key}: invalid value {sv!r}; allowed: {allowed}")
        state[key] = sv
    else:
        raise ValueError(f"unknown option: {key}")
    save_state(state)
    if is_cava:
        # Write cava-state.json and signal the running visualizer
        _write_cava_state_json(state)
        _signal_cava_waybar()
    else:
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
