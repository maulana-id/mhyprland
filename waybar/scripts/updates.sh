#!/usr/bin/env bash
# Waybar custom/updates — counts Debian packages with an available upgrade.
set -u
count=0
if command -v apt >/dev/null 2>&1; then
  count=$(apt list --upgradable 2>/dev/null | grep -c '\[upgradable from:')
fi
if [ "$count" -gt 0 ]; then
  printf '{"text":"%s","tooltip":"%s package update(s) available\\nRun: sudo apt upgrade","class":"has-updates"}\n' "$count" "$count"
else
  printf '{"text":"0","tooltip":"System is up to date","class":"updated"}\n'
fi
