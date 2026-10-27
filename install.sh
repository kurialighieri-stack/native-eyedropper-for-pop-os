#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
bash build.sh
app="$HOME/.local/share/okayu-color-picker"
if [[ -d "$app" ]]; then
  cp -a "$app" "$app.backup-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$app" "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m 644 picker.py libpixel-capture.so "$app/"
cat > "$HOME/.local/bin/native-eyedropper" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 "$HOME/.local/share/okayu-color-picker/picker.py" "$@"
LAUNCHER
chmod +x "$HOME/.local/bin/native-eyedropper"
cat > "$HOME/.local/share/applications/local.okayu.ColorPicker.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Native Eyedropper
Comment=Pick screen colors and copy their HEX code
Exec="$HOME/.local/bin/native-eyedropper" --toggle
Icon=color-select-symbolic
Categories=Graphics;
Terminal=false
StartupNotify=false
DESKTOP
printf 'Installed. Add Super+Alt+8 in COSMIC Settings to run: %s --toggle\n' "$HOME/.local/bin/native-eyedropper"
