#!/usr/bin/env python3
"""BMKG Weather indicator for Waybar.

Fetches Indonesian weather forecast data from the official BMKG API:
https://data.bmkg.go.id/prakiraan-cuaca/

Default location is Jakarta (Kemayoran: 31.71.03.1001).
Customizations are saved locally to ~/.config/waybar/weather.local.json,
which is ignored by Git to keep your dotfiles clean and safe to push.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_CONFIG = {
    "provider": "bmkg",       # "bmkg" or "wttr"
    "adm4": "31.71.03.1001",   # Kemayoran, Kota Adm. Jakarta Pusat (DKI Jakarta)
    "location": "Jakarta",     # City/location string for wttr.in
    "unit": "C",               # C (Celsius) or F (Fahrenheit)
    "lang": "id",              # id (Bahasa Indonesia) or en (English)
    "days": 3,                 # Number of days in tooltip (1-3)
    "show_details": True,      # Show humidity and wind in tooltip
}

WTTR_LANGS = {
    "en", "de", "pl", "ru", "tr", "fr", "be", "zh",
    "es", "pt", "it", "ja", "uk", "sv", "da", "cs", "sk", "ga"
}

CONFIG_FILE = Path.home() / ".config" / "waybar" / "weather.local.json"
CACHE_TTL = 600  # 10 minutes cache

# BMKG weather codes mapping
WEATHER_MAP = {
    0: ("Cerah", "Sunny", "\U000f0599", "\U000f0594", "clear"),
    1: ("Cerah Berawan", "Partly Cloudy", "\U000f0595", "\U000f0f31", "partly-cloudy"),
    2: ("Cerah Berawan", "Partly Cloudy", "\U000f0595", "\U000f0f31", "partly-cloudy"),
    3: ("Berawan", "Mostly Cloudy", "\U000f0590", "\U000f0590", "cloudy"),
    4: ("Berawan Tebal", "Overcast", "\U000f0590", "\U000f0590", "overcast"),
    5: ("Udara Kabur", "Haze", "\U000f0591", "\U000f0591", "haze"),
    10: ("Asap", "Smoke", "\U000f0591", "\U000f0591", "smoke"),
    45: ("Kabut", "Fog", "\U000f0591", "\U000f0591", "fog"),
    60: ("Hujan Ringan", "Light Rain", "\U000f0597", "\U000f0597", "light-rain"),
    61: ("Hujan Ringan / Sedang", "Moderate Rain", "\U000f0597", "\U000f0597", "moderate-rain"),
    63: ("Hujan Lebat", "Heavy Rain", "\U000f0596", "\U000f0596", "heavy-rain"),
    80: ("Hujan Lokal", "Isolated Shower", "\U000f0597", "\U000f0597", "isolated-rain"),
    95: ("Hujan Petir", "Thunderstorm", "\U000f0593", "\U000f0593", "thunderstorm"),
    97: ("Hujan Petir", "Thunderstorm", "\U000f0593", "\U000f0593", "thunderstorm"),
}

DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MONTHS_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des"
]

DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    cfg.update(user_data)
        except Exception:
            pass
    return cfg


def convert_temp(t_c: float | int, unit: str) -> int:
    if str(unit).upper() == "F":
        return round(float(t_c) * 9.0 / 5.0 + 32.0)
    return round(float(t_c))


def format_date(dt: datetime, lang: str) -> str:
    if lang == "en":
        return f"{DAYS_EN[dt.weekday()]}, {dt.day} {MONTHS_EN[dt.month - 1]}"
    return f"{DAYS_ID[dt.weekday()]}, {dt.day} {MONTHS_ID[dt.month - 1]}"


def get_weather_info(code: int, hour: int, lang: str, slot: dict) -> tuple[str, str, str]:
    is_day = 6 <= hour < 18
    default_entry = ("Cerah Berawan", "Partly Cloudy", "\U000f0595", "\U000f0f31", "unknown")
    entry = WEATHER_MAP.get(code, default_entry)

    if lang == "en":
        desc = slot.get("weather_desc_en") or entry[1]
    else:
        desc = slot.get("weather_desc") or entry[0]

    icon = entry[2] if is_day else entry[3]
    css_class = entry[4]
    return desc, icon, css_class


def parse_slot_dt(slot: dict) -> datetime:
    return datetime.strptime(slot["local_datetime"], "%Y-%m-%d %H:%M:%S")


def fetch_from_api(adm4: str) -> dict:
    url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={adm4}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "curl/8.0"}
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_data(adm4: str) -> dict:
    clean_code = adm4.replace(".", "_")
    cache_file = f"/tmp/bmkg_weather_{clean_code}.json"

    # Try valid cache first
    if os.path.exists(cache_file):
        try:
            mtime = os.path.getmtime(cache_file)
            if time.time() - mtime < CACHE_TTL:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    # Fetch fresh data
    try:
        data = fetch_from_api(adm4)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
        return data
    except Exception as e:
        # Fallback to stale cache if API failed
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        raise e


def run_wttrbar(cfg: dict) -> None:
    wttrbar_bin = Path(__file__).resolve().parent.parent / "wttrbar"
    if not wttrbar_bin.exists():
        fallback = {
            "text": "\U000f0590 --",
            "tooltip": "wttrbar binary not found",
            "class": "offline"
        }
        print(json.dumps(fallback, ensure_ascii=False))
        return

    location = cfg.get("location") or "Jakarta"
    unit = str(cfg.get("unit", "C")).upper()
    lang = cfg.get("lang", "en")
    show_details = bool(cfg.get("show_details", True))

    cmd = [str(wttrbar_bin), "--nerd", "--location", location]
    if unit == "F":
        cmd.append("--fahrenheit")
    if lang in WTTR_LANGS:
        cmd.extend(["--lang", lang])
    elif lang == "id":
        cmd.extend(["--lang", "en"])
    if not show_details:
        cmd.append("--hide-conditions")

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            print(res.stdout.strip())
            return
        err = res.stderr.strip() or "wttr.in request failed"
        fallback = {
            "text": "\U000f0590 --",
            "tooltip": f"wttr.in: {err}",
            "class": "offline"
        }
        print(json.dumps(fallback, ensure_ascii=False))
    except Exception as exc:
        fallback = {
            "text": "\U000f0590 --",
            "tooltip": f"wttr.in error: {str(exc)}",
            "class": "offline"
        }
        print(json.dumps(fallback, ensure_ascii=False))


def main() -> None:
    cfg = load_config()

    parser = argparse.ArgumentParser(description="BMKG / wttr.in weather output for Waybar")
    parser.add_argument("--provider", default=None, choices=["bmkg", "wttr"], help="Provider")
    parser.add_argument("--location", default=None, help="wttr.in location")
    parser.add_argument("--adm4", default=None, help="BMKG ADM4 code")
    parser.add_argument("--unit", default=None, choices=["C", "F", "c", "f"], help="Temp unit")
    parser.add_argument("--lang", default=None, choices=["id", "en"], help="Language")
    parser.add_argument("--days", default=None, type=int, help="Forecast days (1-3)")
    args = parser.parse_args()

    provider = args.provider or cfg.get("provider", "bmkg")
    if provider == "wttr":
        if args.location:
            cfg["location"] = args.location
        if args.unit:
            cfg["unit"] = args.unit
        if args.lang:
            cfg["lang"] = args.lang
        run_wttrbar(cfg)
        return

    adm4 = args.adm4 or cfg.get("adm4") or DEFAULT_CONFIG["adm4"]
    unit = (args.unit or cfg.get("unit") or DEFAULT_CONFIG["unit"]).upper()
    lang = args.lang or cfg.get("lang") or DEFAULT_CONFIG["lang"]
    days_limit = args.days or int(cfg.get("days", DEFAULT_CONFIG["days"]))
    show_details = bool(cfg.get("show_details", DEFAULT_CONFIG["show_details"]))

    try:
        data = get_data(adm4)
        lokasi = data["data"][0]["lokasi"]
        cuaca = data["data"][0]["cuaca"]
        flat_slots = [s for day in cuaca for s in day]

        if not flat_slots:
            raise ValueError("No forecast slots returned from BMKG")

        now = datetime.now()
        closest_slot = min(flat_slots, key=lambda s: abs((parse_slot_dt(s) - now).total_seconds()))

        slot_dt = parse_slot_dt(closest_slot)
        desc, icon, css_class = get_weather_info(closest_slot.get("weather", 1), slot_dt.hour, lang, closest_slot)

        raw_t = closest_slot.get("t", 0)
        temp = convert_temp(raw_t, unit)
        humidity = closest_slot.get("hu", 0)
        wind_speed = closest_slot.get("ws", 0)
        wind_dir = closest_slot.get("wd", "-")

        desa = lokasi.get("desa", "")
        kec = lokasi.get("kecamatan", "")
        kotkab = lokasi.get("kotkab", "")

        loc_parts = [p for p in [desa, f"Kec. {kec}" if kec else "", kotkab] if p]
        loc_name = ", ".join(loc_parts) if loc_parts else "BMKG Cuaca"

        unit_str = f"°{unit}"
        temp_line = f"<b>{desc}</b> {temp}{unit_str}"

        tooltip_lines = [
            f"<b>{loc_name}</b>",
            temp_line,
        ]

        if show_details:
            if lang == "en":
                tooltip_lines.append(f"Humidity: {humidity}%")
                tooltip_lines.append(f"Wind: {wind_speed} km/h ({wind_dir})")
            else:
                tooltip_lines.append(f"Kelembapan: {humidity}%")
                tooltip_lines.append(f"Angin: {wind_speed} km/jam ({wind_dir})")

        header_label = "Forecast:" if lang == "en" else "Prakiraan Cuaca:"
        tooltip_lines.append("")
        tooltip_lines.append(f"<b>{header_label}</b>")

        # Group slots by date
        by_date: dict[str, list[tuple[datetime, dict]]] = {}
        for slot in flat_slots:
            sdt = parse_slot_dt(slot)
            dstr = sdt.strftime("%Y-%m-%d")
            by_date.setdefault(dstr, []).append((sdt, slot))

        today_str = now.strftime("%Y-%m-%d")

        for dstr, slots in list(by_date.items())[:days_limit]:
            first_dt = slots[0][0]
            if dstr == today_str:
                day_title = "Today" if lang == "en" else "Hari Ini"
                day_label = f"{day_title} ({format_date(first_dt, lang)})"
            else:
                day_label = format_date(first_dt, lang)

            tooltip_lines.append(f"\n<b>{day_label}</b>")
            for sdt, slot in slots:
                s_desc, s_icon, _ = get_weather_info(slot.get("weather", 1), sdt.hour, lang, slot)
                s_temp = convert_temp(slot.get("t", 0), unit)
                s_hu = slot.get("hu", 0)
                time_str = sdt.strftime("%H:%M")
                if show_details:
                    tooltip_lines.append(f"{time_str}  {s_icon}  {s_temp}°  {s_desc} (RH {s_hu}%)")
                else:
                    tooltip_lines.append(f"{time_str}  {s_icon}  {s_temp}°  {s_desc}")

        output = {
            "text": f"{icon} {temp}",
            "tooltip": "\n".join(tooltip_lines),
            "class": css_class
        }
        print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        err_msg = f"BMKG Cuaca: {str(e)}"
        output = {
            "text": "\U000f0590 --",
            "tooltip": err_msg,
            "class": "offline"
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
