# Native Eyedropper for Pop!_OS

A native Wayland color picker for the COSMIC desktop: a live color-ring cursor and a small, persistent window with the selected color and a copyable HEX code.

**Created with AI assistance (OpenAI Codex), under human direction.** The implementation and this documentation were generated and iterated with AI. This is an independent community project, unaffiliated with System76 or the Wayland project.

## Features

- A pipette cursor surrounded by a ring showing the sampled pixel color.
- Click anywhere on a supported desktop output to select a color.
- Copy the selected `#RRGGBB` value from a purple, dark-themed popup.
- Toggle sampling without closing the selected-color window; its close button dismisses it.
- Multiple outputs, including the tested 125% fractional-scaling setup.
- User-local installation, with no privileged background service.

## Requirements and compatibility

Developed on Pop!_OS 24.04 with COSMIC 1.11.0 and Wayland. Requires `zwlr_layer_shell_v1`, `ext_output_image_capture_source_manager_v1`, and `ext_image_copy_capture_manager_v1`. Other desktops and older COSMIC versions are not verified. X11 is unsupported.

Install dependencies:

```sh
sudo apt update
sudo apt install build-essential pkg-config libwayland-dev python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```

Runtime components are Python 3, GTK 3, PyGObject, Cairo, GtkLayerShell, and libwayland-client. GCC and pkg-config build the native library. Generated Wayland bindings are included, so a scanner is not needed for normal installation.

## Install

```sh
git clone https://github.com/kurialighieri-stack/native-eyedropper-for-pop-os.git
cd native-eyedropper-for-pop-os
bash install.sh
```

The installer builds from source and installs into `~/.local/share/okayu-color-picker`, with a launcher in `~/.local/bin/native-eyedropper` and an application-menu entry. An existing application directory is backed up before replacement. The existing application ID and storage directory are retained for compatibility with the original personal installation.

In **COSMIC Settings → Input devices → Keyboard → Custom shortcuts**, add **Super+Alt+8** with this command (replace `/home/YOUR_USER` with your home directory):

```text
/home/YOUR_USER/.local/bin/native-eyedropper --toggle
```

The installer deliberately leaves your shortcut configuration to COSMIC Settings and preserves unrelated bindings. Ensure the chosen shortcut is available. No autostart is needed: the shortcut launches the single-instance application on demand.

## Use

Press the shortcut to enable sampling. The ring follows the color under the cursor. Left-click to update the color window, then select another pixel if desired. Press the shortcut again, Escape, or right-click to restore normal pointer operation. The selected-color window remains open until you close it.

```sh
~/.local/bin/native-eyedropper --toggle
~/.local/bin/native-eyedropper --status
~/.local/bin/native-eyedropper --show-color '#A785D8'
~/.local/bin/native-eyedropper --quit
```

`--idle` starts the application without enabling sampling. With no arguments, the command toggles sampling. `--status` starts an idle instance if none exists.

## How it works

`picker.py` owns the GTK application, transparent layer-shell selection surfaces, cursor, clipboard, and color window. A background thread calls `libpixel-capture.so` through ctypes. `pixel_capture.c` connects to Wayland and captures outputs into anonymous shared-memory buffers using the compositor's image-copy protocols. The cursor is drawn separately and is not requested as part of capture. Monitor origins associate GTK surfaces with captured outputs; pointer coordinates are normalized to each output.

The application does not save screen images. The last selected HEX value is saved to `$XDG_STATE_HOME/okayu-color-picker/selection.json` (default `~/.local/state`). While sampling, screen contents are available in process memory. Selection surfaces temporarily intercept input across outputs; stop sampling to interact normally with other applications. Protected surfaces or compositor restrictions may prevent capture. HDR/color-managed output, rotated displays, hotplugging, and other compositors have not been comprehensively tested. HEX values describe captured 8-bit RGB pixels, not calibrated physical display colors.

## Updates and recovery

All installed files are user-local, so ordinary system package upgrades should not overwrite them. Compatibility still depends on the compositor protocols and GTK libraries. After a major COSMIC upgrade, rebuild and retest:

```sh
~/.local/bin/native-eyedropper --quit
git pull --ff-only
bash install.sh
```

If activation fails, run the command from a terminal to inspect errors. Verify that you are in a COSMIC Wayland session and that the listed protocol versions remain supported. Reinstalling the project cannot add missing compositor protocols. Installation backups sit beside the application directory and may be restored manually after quitting the application.

To uninstall, quit the application, remove its custom shortcut in COSMIC Settings, then remove `~/.local/bin/native-eyedropper`, `~/.local/share/applications/local.okayu.ColorPicker.desktop`, and `~/.local/share/okayu-color-picker`. Remove the state directory only if you also want to erase the remembered color. The original personal `cuentagotas` launcher, if present, points to the same application and should also be removed or updated.

## Development and validation

```sh
bash build.sh
python3 -m py_compile picker.py
python3 -m unittest test_core
bash -n install.sh build.sh
```

The original implementation was manually exercised on a three-monitor COSMIC desktop, including exact-color capture checks, live changes, and persistence of the color window after sampling stops. Automated unit tests cover color formatting and selection persistence; they do not replace a real Wayland-session test. To test manually, display a known solid RGB patch, select it, compare its HEX value, toggle sampling off, and verify that Copy HEX and the close button still work. Repeat on every output and scaling configuration.

## License

Original project code is MIT-licensed. Vendored Wayland protocol definitions and generated bindings retain their upstream copyright and license notices; see [THIRD_PARTY.md](THIRD_PARTY.md).
