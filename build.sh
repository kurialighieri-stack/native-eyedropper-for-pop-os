#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
gcc -shared -fPIC -O2 pixel_capture.c capture.c source.c foreign.c workspace.c cosmic-source.c -o libpixel-capture.so $(pkg-config --cflags --libs wayland-client)
gcc -shared -fPIC -O2 cosmic-effects.c ext-background-effect-v1-protocol.c corners.c -o libcosmic-effects.so $(pkg-config --cflags --libs wayland-client) -l:libgtk-layer-shell.so.0 -lm
for lang in es pt_BR; do
  mkdir -p "locale/$lang/LC_MESSAGES"
  msgfmt --check "$lang.po" -o "locale/$lang/LC_MESSAGES/okayu-picker.mo"
done
