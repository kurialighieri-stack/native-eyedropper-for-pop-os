#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
gcc -shared -fPIC -O2 pixel_capture.c capture.c source.c foreign.c -o libpixel-capture.so $(pkg-config --cflags --libs wayland-client)
