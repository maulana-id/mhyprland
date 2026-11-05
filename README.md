# Ascent — a full Hyprland desktop

Hyprland desktop configuration for Waybar, kitty, hyprlock, dunst, hyprpaper, and Hyprlauncher. A shared theme engine applies palettes across the desktop; the GTK Control Center manages themes, wallpapers, and layout options.

![Hypr Control Center](hypr/assets/screenshot-themes.png)

## Install

Clone this repository to `~/.config`, then run the bootstrap script:

```bash
git clone <repo-url> ~/.config
~/.config/hypr/scripts/bootstrap
~/.config/hypr/scripts/hypr-control-center
```

Requires Hyprland 0.55+ with the Lua config provider, Python 3.11+ with PyGObject, Nerd Fonts, and the desktop tools used by the configuration: Waybar, kitty, hyprlock, hypridle, hyprlauncher, hyprshutdown, hyprsunset, hyprpolkitagent, dunst, grim, slurp, wl-clipboard, cliphist, brightnessctl, playerctl, btop, cava, ImageMagick, hyprpaper, and hyprpicker. Bootstrap checks dependencies and installs local extras when possible.

On Debian, install the system packages with:

```bash
sudo apt install hyprland waybar kitty hyprlock hypridle hyprlauncher hyprshutdown \
  hyprsunset hyprpolkitagent dunst grim slurp wl-clipboard cliphist brightnessctl \
  playerctl btop cava imagemagick python3-gi hyprpaper hyprpicker
```

## Commands

```bash
theme-switch list
theme-switch set nord
theme-switch next
theme-switch apply
theme-switch option blur on

wallpaper-set ~/Pictures/Wallpapers/image.png
wallpaper-set --random
wallpaper-set --directory ~/Pictures/Wallpapers

waybar-mode --layout compact --position bottom
waybar-mode --list

hypr-control-center --tab theme
```

The Control Center also has wallpaper, bar, desktop, and keybind tabs. `SUPER + SHIFT + T` opens it; `SUPER + ALT + T` changes the theme.

## Customize

- Themes: `hypr/themes/*.toml`
- Templates: `hypr/templates/`
- Waybar layouts: `waybar/presets/`
- Wallpapers: `~/Pictures/Wallpapers/`

Run `theme-switch apply` to regenerate the app palettes from the current theme. Generated configuration files are tracked so a fresh clone works immediately.

Machine-local customization state lives in `hypr/theme-state.local.json` and `waybar/cava-state.json`; both are gitignored. Paths are written with `~/` so generated configs stay portable. Delete the local state to fall back to the defaults in [theme_engine.py](hypr/scripts/theme_engine.py).

## Repository

This repository lives at `~/.config`. `.gitignore` allows only `hypr/`, `waybar/`, `kitty/`, `dunst/`, `README.md`, and `.gitignore`; other desktop and application data stays out of Git. Check `git status` before committing.

Waybar logs are in `~/.cache/waybar.log`; the IPC shim log is `~/.cache/waybar-ipc-proxy.log`. Start Waybar through `~/.config/waybar/scripts/start-waybar` so workspace actions use the Hyprland IPC shim.

The shim also mirrors the real instance's `.hyprpaper.sock`, `.hyprsunset.sock` and event socket into the proxy directory (and refreshes them every couple of seconds). That is what allows tools launched from Waybar — the Hyprsunset slider, scroll-to-adjust gamma, and the wallpaper picker — to talk to hyprsunset/hyprpaper while Waybar is using the proxy signature.

Do not enable `waybar.service`: it starts a second bare Waybar without the IPC shim. This setup starts Waybar only from `hyprland.lua` via `start-waybar`; the user service is masked and its original file is kept as `~/.config/systemd/user/waybar.service.disabled`.
