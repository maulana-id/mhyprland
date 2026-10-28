#!/usr/bin/env python3
"""Compatibility shim for Waybar 0.12 on Hyprland 0.55+.

Waybar 0.12 clicks a workspace by writing legacy commands such as

    dispatch workspace 2

to Hyprland's command socket. Hyprland 0.55 uses the Lua config provider and
parses that socket payload as Lua, so the legacy command fails. This proxy sits
between Waybar and the real Hyprland socket, translates the handful of legacy
dispatch commands Waybar emits, and forwards everything else untouched.

Waybar is launched with HYPRLAND_INSTANCE_SIGNATURE pointing at the proxy
directory, whose .socket2.sock is a symlink to the real event socket.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from pathlib import Path


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def lua_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rewrite_request(request: str) -> str:
    """Translate legacy Hyprland dispatches into the Lua dispatcher API."""
    if not request.startswith("dispatch "):
        return request
    body = request[len("dispatch "):].strip()

    # Waybar's hyprland/workspaces click handler.
    if body.startswith("workspace "):
        arg = body[len("workspace "):].strip()
        return f"dispatch hl.dsp.focus({{ workspace = {lua_string(arg)} }})"

    if body.startswith("focusworkspaceoncurrentmonitor "):
        arg = body[len("focusworkspaceoncurrentmonitor "):].strip()
        return (
            "dispatch hl.dsp.focus({ workspace = "
            f"{lua_string(arg)}, on_current_monitor = true }})"
        )

    if body == "togglespecialworkspace":
        return "dispatch hl.dsp.workspace.toggle_special()"

    if body.startswith("togglespecialworkspace "):
        arg = body[len("togglespecialworkspace "):].strip()
        return f"dispatch hl.dsp.workspace.toggle_special({lua_string(arg)})"

    # Common legacy commands emitted by ancillary tools (e.g. hyprshutdown).
    if body == "exit":
        return "dispatch hl.dsp.exit()"
    if body == "killactive":
        return "dispatch hl.dsp.window.close()"
    if body == "togglefloating":
        return "dispatch hl.dsp.window.float({ action = \"toggle\" })"
    if body.startswith("exec "):
        command = body[len("exec "):]
        return f"dispatch hl.dsp.exec_cmd({lua_string(command)})"

    return request


class WaybarIPCProxy:
    def __init__(self, real_sig: str, proxy_sig: str) -> None:
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "hypr"
        self.real_dir = runtime / real_sig
        self.proxy_dir = runtime / proxy_sig
        self.real_socket = self.real_dir / ".socket.sock"
        self.proxy_socket = self.proxy_dir / ".socket.sock"
        self.event_socket = self.proxy_dir / ".socket2.sock"
        self.real_event = self.real_dir / ".socket2.sock"
        self.running = True

    def prepare(self) -> None:
        self.proxy_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.proxy_dir, 0o700)
        (self.proxy_dir / "real-sig").write_text(self.real_dir.name, encoding="utf-8")
        if self.proxy_socket.exists() or self.proxy_socket.is_symlink():
            self.proxy_socket.unlink()
        if self.event_socket.exists() or self.event_socket.is_symlink():
            self.event_socket.unlink()
        self.event_socket.symlink_to(self.real_event)

    def forward(self, request: str) -> bytes:
        buffer = bytearray()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(8)
        try:
            client.connect(str(self.real_socket))
            client.sendall(request.encode("utf-8", errors="replace"))
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                buffer.extend(chunk)
        except OSError as exc:
            return f"error: Hyprland IPC proxy: {exc}".encode()
        finally:
            client.close()
        return bytes(buffer)

    def handle(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(2)
            raw = connection.recv(65536)
            if not raw:
                return
            request = raw.decode("utf-8", errors="replace").rstrip("\x00\n")
            rewritten = rewrite_request(request)
            if rewritten != request:
                log(f"rewrite: {request!r} -> {rewritten!r}")
            connection.sendall(self.forward(rewritten))
        except OSError as exc:
            log(f"connection error: {exc}")
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def serve(self) -> None:
        self.prepare()
        if self.proxy_socket.exists():
            self.proxy_socket.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.proxy_socket))
        os.chmod(self.proxy_socket, 0o600)
        server.listen(64)
        (self.proxy_dir / "proxy.pid").write_text(str(os.getpid()), encoding="utf-8")
        log(f"Waybar IPC proxy ready: {self.proxy_socket} -> {self.real_socket}")

        while self.running:
            try:
                connection, _ = server.accept()
            except OSError:
                break
            threading.Thread(target=self.handle, args=(connection,), daemon=True).start()

        server.close()
        try:
            self.proxy_socket.unlink()
        except OSError:
            pass

    def stop(self, *_args) -> None:
        self.running = False
        try:
            self.proxy_socket.unlink()
        except OSError:
            pass


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} REAL_INSTANCE_SIGNATURE PROXY_SIGNATURE", file=sys.stderr)
        return 2
    proxy = WaybarIPCProxy(sys.argv[1], sys.argv[2])
    signal.signal(signal.SIGTERM, proxy.stop)
    signal.signal(signal.SIGINT, proxy.stop)
    proxy.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
