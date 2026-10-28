#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
bash build.sh
app="$HOME/.local/share/okayu-color-picker"
if [[ -d "$app" ]]; then
  cp -a "$app" "$app.backup-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$app" "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m 644 picker.py picker_model.py magnifier.py cosmic_style.py libpixel-capture.so libcosmic-effects.so "$app/"
mkdir -p "$app/locale"
cp -a locale/. "$app/locale/"
cat > "$HOME/.local/bin/native-eyedropper" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 "$HOME/.local/share/okayu-color-picker/picker.py" "$@"
LAUNCHER
chmod +x "$HOME/.local/bin/native-eyedropper"
cat > "$HOME/.local/share/applications/local.okayu.ColorPicker.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Okayu Color Picker
Comment=Pick, compare and organize screen colors
Comment[es]=Selecciona, compara y organiza colores de la pantalla
Comment[pt_BR]=Selecione, compare e organize cores da tela
Exec="$HOME/.local/bin/native-eyedropper" --toggle
Icon=color-select-symbolic
Categories=Graphics;
Terminal=false
StartupNotify=false
DESKTOP
printf 'Installed. Add Super+Alt+8 in COSMIC Settings to run: %s --toggle\n' "$HOME/.local/bin/native-eyedropper"
