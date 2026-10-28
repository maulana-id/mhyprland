#!/usr/bin/env python3
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

class HyprsunsetControl(Gtk.Window):
    def __init__(self):
        super().__init__(title="Hyprsunset Control")
        self.set_border_width(12)
        self.set_default_size(280, 140)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)

        # Close popup automatically when clicking away
        self.connect("focus-out-event", lambda w, e: Gtk.main_quit())

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(box)

        # Gamma / Brightness Slider
        lbl_gamma = Gtk.Label(label="<b>Brightness / Gamma</b>")
        lbl_gamma.set_use_markup(True)
        box.pack_start(lbl_gamma, False, False, 0)

        self.scale_gamma = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 5)
        self.scale_gamma.set_value(100)
        self.scale_gamma.connect("value-changed", self.on_gamma_changed)
        box.pack_start(self.scale_gamma, False, False, 0)

        # Color Temperature Slider (Kelvin)
        lbl_temp = Gtk.Label(label="<b>Color Temp (1000K - 6500K)</b>")
        lbl_temp.set_use_markup(True)
        box.pack_start(lbl_temp, False, False, 0)

        self.scale_temp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1000, 6500, 250)
        self.scale_temp.set_value(6500)
        self.scale_temp.connect("value-changed", self.on_temp_changed)
        box.pack_start(self.scale_temp, False, False, 0)

        self.show_all()

    def on_gamma_changed(self, widget):
        val = int(widget.get_value())
        subprocess.run(["hyprctl", "hyprsunset", "gamma", str(val)], check=False)

    def on_temp_changed(self, widget):
        val = int(widget.get_value())
        subprocess.run(["hyprctl", "hyprsunset", "temperature", str(val)], check=False)

if __name__ == "__main__":
    win = HyprsunsetControl()
    Gtk.main()
