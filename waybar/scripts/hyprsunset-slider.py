#!/usr/bin/env python3
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

class HyprsunsetControl(Gtk.Window):
    def __init__(self):
        super().__init__(title="Light & color")
        self.set_name("hyprsunset-popup")
        self.set_border_width(18)
        self.set_default_size(350, 377)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.pending_updates = {}
        self.apply_style()
        self.connect("key-press-event", self.on_key_press)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.add(content)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        heading.set_halign(Gtk.Align.START)
        title = Gtk.Label(label="Light & color")
        title.get_style_context().add_class("title")
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="HYPRSUNSET  /  DISPLAY TUNING")
        subtitle.get_style_context().add_class("eyebrow")
        subtitle.set_halign(Gtk.Align.START)
        heading.pack_start(title, False, False, 0)
        heading.pack_start(subtitle, False, False, 0)
        close_button = Gtk.Button(label="×")
        close_button.set_tooltip_text("Close")
        close_button.get_style_context().add_class("close-button")
        close_button.connect("clicked", self.close_popup)
        header.pack_start(heading, True, True, 0)
        header.pack_end(close_button, False, False, 0)
        content.pack_start(header, False, False, 0)

        content.pack_start(Gtk.Separator(), False, False, 0)

        self.scale_temp, self.temp_value = self.add_control(
            content, "COLOR TEMPERATURE", 1000, 6500, 250, 6500, " K", self.on_temp_changed
        )

        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        for label, temperature in (("Warm", 3000), ("Balanced", 4500), ("Daylight", 6500)):
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("preset")
            button.connect("clicked", self.set_temperature, temperature)
            presets.pack_start(button, True, True, 0)
        content.pack_start(presets, False, False, 0)

        self.scale_gamma, self.gamma_value = self.add_control(
            content, "GAMMA", 10, 100, 5, 100, "%", self.on_gamma_changed
        )

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        note = Gtk.Label(label="100% gamma  /  6500 K")
        note.get_style_context().add_class("hint")
        note.set_halign(Gtk.Align.START)
        reset = Gtk.Button(label="Reset")
        reset.get_style_context().add_class("reset")
        reset.connect("clicked", self.reset_controls)
        footer.pack_start(note, True, True, 0)
        footer.pack_end(reset, False, False, 0)
        content.pack_end(footer, False, False, 0)

        self.show_all()

    def apply_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            window#hyprsunset-popup {
                background-color: #191d23;
                color: #edf0f2;
                border: 1px solid #39424b;
                border-radius: 10px;
            }
            label { color: #edf0f2; }
            label.title { font-size: 19px; font-weight: bold; }
            label.eyebrow { color: #9da8ae; font-size: 9px; font-weight: bold; }
            label.control-name { color: #b7c0c5; font-size: 10px; font-weight: bold; }
            label.readout { color: #f0b56d; font-size: 17px; font-weight: bold; }
            label.hint { color: #9da8ae; font-size: 10px; }
            separator { background-color: #343c45; min-height: 1px; }
            scale trough { background-color: #343c45; border-radius: 4px; min-height: 6px; }
            scale highlight { background-color: #e8a85f; border-radius: 4px; }
            scale slider {
                background-color: #f0b56d;
                border: 2px solid #191d23;
                border-radius: 10px;
                min-width: 16px;
                min-height: 16px;
            }
            button.preset, button.reset {
                background-color: #282f36;
                background-image: none;
                border: 1px solid #3b454d;
                border-radius: 6px;
                color: #dce1e3;
                padding: 6px 9px;
            }
            button.close-button {
                background-color: #282f36;
                background-image: none;
                border: 1px solid #3b454d;
                border-radius: 6px;
                color: #dce1e3;
                min-width: 24px;
                min-height: 24px;
                padding: 0;
            }
            button.preset:hover, button.reset:hover {
                background-color: #35413f;
                border-color: #78a99c;
                color: #ffffff;
            }
            button.close-button:hover {
                background-color: #7d4141;
                border-color: #a85b5b;
                color: #ffffff;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def add_control(self, parent, name, minimum, maximum, step, initial, unit, callback):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label=name)
        title.get_style_context().add_class("control-name")
        title.set_halign(Gtk.Align.START)
        value = Gtk.Label(label=f"{initial}{unit}")
        value.get_style_context().add_class("readout")
        value.set_halign(Gtk.Align.END)
        header.pack_start(title, True, True, 0)
        header.pack_end(value, False, False, 0)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimum, maximum, step)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.set_value(initial)
        scale.connect("value-changed", callback, value, unit)
        parent.pack_start(header, False, False, 0)
        parent.pack_start(scale, False, False, 0)
        return scale, value

    def schedule_update(self, key, command):
        source_id = self.pending_updates.pop(key, None)
        if source_id is not None:
            GLib.source_remove(source_id)
        self.pending_updates[key] = GLib.timeout_add(70, self.run_update, key, command)

    def run_update(self, key, command):
        self.pending_updates.pop(key, None)
        subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return GLib.SOURCE_REMOVE

    def set_temperature(self, button, temperature):
        _ = button
        self.scale_temp.set_value(temperature)

    def reset_controls(self, _button):
        _ = _button
        self.scale_gamma.set_value(100)
        self.scale_temp.set_value(6500)

    def close_popup(self, button):
        _ = button
        Gtk.main_quit()

    def on_key_press(self, _widget, event):
        _ = _widget
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False

    def on_gamma_changed(self, widget, value_label, unit):
        val = int(widget.get_value())
        value_label.set_text(f"{val}{unit}")
        self.schedule_update("gamma", ["hyprctl", "hyprsunset", "gamma", str(val)])

    def on_temp_changed(self, widget, value_label, unit):
        val = int(widget.get_value())
        value_label.set_text(f"{val}{unit}")
        self.schedule_update("temperature", ["hyprctl", "hyprsunset", "temperature", str(val)])

if __name__ == "__main__":
    GLib.set_prgname("hyprsunset-slider")
    GLib.set_application_name("Hyprsunset Slider")
    Gdk.set_program_class("hyprsunset-slider")
    win = HyprsunsetControl()
    Gtk.main()
