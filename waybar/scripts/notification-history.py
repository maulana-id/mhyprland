#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

READ_ICON = "󰂚"
UNREAD_ICON = "󱅫"
STATE_ROOT = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
STATE_FILE = STATE_ROOT / "waybar" / "notification-history.json"


def run_dunst(*args):
    return subprocess.run(
        ["dunstctl", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout.strip()


def unwrap(value):
    if isinstance(value, dict) and "type" in value and "data" in value:
        return unwrap(value["data"])
    if isinstance(value, dict):
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


def find_records(value):
    if isinstance(value, list):
        if value and all(isinstance(item, dict) and "id" in item for item in value):
            return value
        for item in value:
            records = find_records(item)
            if records:
                return records
    elif isinstance(value, dict):
        for item in value.values():
            records = find_records(item)
            if records:
                return records
    return []


def get_history():
    response = json.loads(run_dunst("history"))
    records = find_records(unwrap(response))
    return sorted(records, key=lambda item: int(item.get("id", 0)), reverse=True)


def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_seen(ids):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"seen_ids": sorted(set(ids))}), encoding="utf-8")
    temporary.replace(STATE_FILE)


def status():
    try:
        records = get_history()
        ids = {str(item["id"]) for item in records}
        state = read_state()
        if state is None:
            write_seen(ids)
            unread_ids = set()
        else:
            unread_ids = ids - {str(item) for item in state.get("seen_ids", [])}
        unread_count = len(unread_ids)
        print(json.dumps({
            "text": UNREAD_ICON if unread_count else READ_ICON,
            "class": "unread" if unread_count else "read",
            "tooltip": f"Notification history · {unread_count} unread",
        }, ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as error:
        print(json.dumps({
            "text": READ_ICON,
            "class": "unavailable",
            "tooltip": f"Dunst unavailable: {error}",
        }, ensure_ascii=False))


class NotificationHistory(Gtk.Window):
    def __init__(self):
        super().__init__(title="Notification history")
        self.set_name("notification-history")
        self.set_default_size(420, 520)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.connect("key-press-event", self.on_key_press)
        self.apply_style()

        try:
            self.records = get_history()
            write_seen(str(item["id"]) for item in self.records)
            self.error = None
        except (OSError, ValueError, subprocess.SubprocessError, KeyError) as error:
            self.records = []
            self.error = str(error)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_border_width(16)
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title = Gtk.Label(label="Notifications")
        title.get_style_context().add_class("title")
        title.set_halign(Gtk.Align.START)
        subtitle_text = f"{len(self.records)} SAVED"
        subtitle = Gtk.Label(label=subtitle_text)
        subtitle.get_style_context().add_class("eyebrow")
        subtitle.set_halign(Gtk.Align.START)
        title_box.pack_start(title, False, False, 0)
        title_box.pack_start(subtitle, False, False, 0)

        close_button = Gtk.Button(label="×")
        close_button.set_tooltip_text("Close")
        close_button.get_style_context().add_class("close-button")
        close_button.connect("clicked", self.close_popup)
        header.pack_start(title_box, True, True, 0)
        header.pack_end(close_button, False, False, 0)
        root.pack_start(header, False, False, 0)
        root.pack_start(Gtk.Separator(), False, False, 0)

        if self.error:
            empty = Gtk.Label(label=f"Could not read Dunst history\n{self.error}")
            empty.set_line_wrap(True)
            empty.get_style_context().add_class("empty")
            root.pack_start(empty, True, True, 0)
        elif not self.records:
            empty = Gtk.Label(label="No notifications in history")
            empty.get_style_context().add_class("empty")
            root.pack_start(empty, True, True, 0)
        else:
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_min_content_height(300)
            list_box = Gtk.ListBox()
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)
            for record in self.records:
                list_box.add(self.create_row(record))
            scroller.add(list_box)
            root.pack_start(scroller, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hint = Gtk.Label(label="Click a notification to show it again")
        hint.get_style_context().add_class("hint")
        hint.set_halign(Gtk.Align.START)
        clear_button = Gtk.Button(label="Clear history")
        clear_button.get_style_context().add_class("clear-button")
        clear_button.connect("clicked", self.clear_history)
        footer.pack_start(hint, True, True, 0)
        footer.pack_end(clear_button, False, False, 0)
        root.pack_start(footer, False, False, 0)
        self.show_all()

    def apply_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            window#notification-history {
                background-color: #191d23;
                color: #edf0f2;
                border: 1px solid #39424b;
                border-radius: 10px;
            }
            label { color: #edf0f2; }
            label.title { font-size: 19px; font-weight: bold; }
            label.eyebrow { color: #9da8ae; font-size: 9px; font-weight: bold; }
            label.appname { color: #e8a85f; font-size: 10px; font-weight: bold; }
            label.summary { font-size: 13px; font-weight: bold; }
            label.body, label.empty { color: #b7c0c5; }
            label.hint { color: #9da8ae; font-size: 10px; }
            separator { background-color: #343c45; min-height: 1px; }
            list row { background: transparent; padding: 3px 0; }
            .notification-card {
                background-color: #242a31;
                border: 1px solid #343d46;
                border-radius: 7px;
                padding: 11px;
            }
            button.close-button, button.clear-button, button.replay-button {
                background-color: #282f36;
                background-image: none;
                border: 1px solid #3b454d;
                border-radius: 6px;
                color: #dce1e3;
                padding: 6px 9px;
            }
            button.close-button { min-width: 24px; min-height: 24px; padding: 0; }
            button:hover {
                background-color: #35413f;
                border-color: #78a99c;
                color: #ffffff;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def create_row(self, record):
        row = Gtk.ListBoxRow()
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.get_style_context().add_class("notification-card")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        appname = Gtk.Label(label=str(record.get("appname") or "Notification"))
        appname.get_style_context().add_class("appname")
        appname.set_halign(Gtk.Align.START)
        urgency = Gtk.Label(label=str(record.get("urgency") or "normal").upper())
        urgency.get_style_context().add_class("eyebrow")
        urgency.set_halign(Gtk.Align.END)
        header.pack_start(appname, True, True, 0)
        header.pack_end(urgency, False, False, 0)
        card.pack_start(header, False, False, 0)

        summary = Gtk.Label(label=str(record.get("summary") or "(no title)"))
        summary.get_style_context().add_class("summary")
        summary.set_halign(Gtk.Align.START)
        summary.set_line_wrap(True)
        card.pack_start(summary, False, False, 0)
        body_text = str(record.get("body") or "")
        if body_text:
            body = Gtk.Label(label=body_text)
            body.get_style_context().add_class("body")
            body.set_halign(Gtk.Align.START)
            body.set_line_wrap(True)
            body.set_xalign(0)
            card.pack_start(body, False, False, 0)
        row.add(card)
        row.connect("activate", self.replay, int(record["id"]))
        return row

    def replay(self, _row, notification_id):
        _ = _row
        subprocess.run(
            ["dunstctl", "history-pop", str(notification_id)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def clear_history(self, _button):
        _ = _button
        subprocess.run(
            ["dunstctl", "history-clear"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        write_seen([])
        Gtk.main_quit()

    def close_popup(self, _button):
        _ = _button
        Gtk.main_quit()

    def on_key_press(self, _widget, event):
        _ = _widget
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        status()
        return
    GLib.set_prgname("notification-history")
    GLib.set_application_name("Notification History")
    Gdk.set_program_class("notification-history")
    window = NotificationHistory()
    Gtk.main()
    window.destroy()


if __name__ == "__main__":
    main()