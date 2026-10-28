# Okayu Color Picker for Pop!_OS

A native Wayland color picker for the COSMIC desktop: a comparison-ring cursor with a pixel magnifier, theme-aware floating windows, and persistent color palettes.

**Created with AI assistance (OpenAI Codex), under human direction.** The implementation and this documentation were generated and iterated with AI. This is an independent community project, unaffiliated with System76 or the Wayland project.

**Version 0.2.0 — development snapshot.** Automated checks cover the current implementation; physical mixed-scale drag validation is still pending. See [VALIDATION.md](VALIDATION.md) for the exact coverage and remaining checks.

## Features

- A pipette cursor with a comparison ring: live pixel color on top, last selected color on the bottom. Before the first selection, both halves show the live color.
- Click anywhere on a supported desktop output to select a color.
- Copy colors as HEX, RGB, HSL or approximate CMYK. One global format drives the selected-color window, palette tooltips and context-menu copy action.
- Live COSMIC colors, accents and frosted backgrounds; color swatches stay opaque.
- English, Spanish and Brazilian Portuguese (pt-BR), with automatic locale detection and a manual language preference.
- A nearest-neighbor pixel magnifier beside the comparison ring, with wheel-controlled 1×, 2×, 4×, 8× and 16× zoom.
- Right-click while sampling to save the last selected color to a compact palette, without duplicates.
- Save/load named `.gpl` palette files, clear the working palette with confirmation, and right-click swatches in normal mode to copy the current color format or delete a color.
- Sample palette swatches with the eyedropper, or click them in normal pointer mode to select their original RGB color.
- Super+left-drag or middle-button-drag either window between outputs, preserving the pointer hotspot. Positions and palette colors are remembered.
- Toggle sampling without closing the selected-color window; its close button dismisses it.
- Multiple outputs, including the tested 125% fractional-scaling setup.
- User-local installation, with no privileged background service.

## Requirements and compatibility

Developed on Pop!_OS 24.04 with COSMIC 1.11.0 and Wayland. Requires `zwlr_layer_shell_v1`, `ext_output_image_capture_source_manager_v1`, and `ext_image_copy_capture_manager_v1`. Correct custom-cursor exclusion in the current COSMIC build additionally uses `ext_workspace_manager_v1` and `zcosmic_workspace_image_capture_source_manager_v1`. Other desktops and older COSMIC versions are not verified. X11 is unsupported.

Install dependencies:

```sh
sudo apt update
sudo apt install build-essential pkg-config libwayland-dev gettext python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```

Runtime components are Python 3, GTK 3, PyGObject, Cairo, GtkLayerShell, and libwayland-client. GCC and pkg-config build the capture/effects libraries; gettext/msgfmt compiles the translation catalogs. The optional `ext_background_effect_manager_v1` protocol enables native blur. On COSMIC, `cosmic_corner_radius_manager_v1` version 2 supplies native layer-corner clipping. The effects bridge links the existing gtk-layer-shell runtime for its public layer-surface accessor; no GTK development headers are required. It is not required for capture; without blur support, window backgrounds stay opaque. Generated Wayland bindings are included, so a scanner is not needed for normal installation.

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

Press the shortcut to enable sampling. Left-click to update the selected-color window. The upper half of the ring follows the pixel under the cursor, while its lower half preserves your last selection for comparison. Right-click saves **the selected color**, not the current hover color, to the palette. Repeated colors are ignored. With no selected color, right-click does nothing.

The palette first appears below the selected-color window. It contains small swatches and its own close button; the swatches wrap into rows and scroll when needed. While sampling, click a swatch to sample its actual displayed pixel. In normal pointer mode, click a swatch to put its stored RGB value in the selected-color window, then use Copy in the current display format. Right-click is no longer a cancel gesture: press **Super+Alt+8 or Escape** to return to normal pointer operation. Both windows remain open.

In normal pointer mode, hold **Super and drag with the left mouse button anywhere in either window**, including its buttons and color-code field. Alternatively, drag using the middle mouse button without modifiers. The compositor moves a visual copy at the exact grab offset across outputs; releasing places the real window on the output under the pointer. Escape cancels an in-progress native drag and restores the original position. Windows move independently. Each window has its own × button, usable even while sampling. Closing the palette preserves its saved colors and leaves the selected-color window open. You can also focus the palette in normal mode and press Escape to dismiss it. Right-click in sampling mode reopens the saved palette.

The palette toolbar has **Save**, **Load**, and **Clear** icons on the left, with preferences and its independent close button on the right:

- **Save** opens the system file chooser so you can name the palette and choose a location. Before opening it, the app creates `Palette` inside your XDG Pictures directory if necessary (for example, `~/Pictures/Palette` or `~/Imágenes/Palette`). The initial filename is `Untitled.gpl`; exports always use the lowercase `.gpl` extension, and the filename supplies the palette name inside the file. Existing destinations require overwrite confirmation.
- **Load** opens an existing GIMP RGB palette and replaces the working colors only after validating the complete file. Duplicates are removed in order. Invalid files leave the current palette intact and show an error.
- **Clear** asks for confirmation, with **Cancel** selected by default. Confirming empties the working palette; saved files and the selected-color window are preserved.

In normal pointer mode, **right-click a swatch** for **Copy HEX/RGB/HSL/CMYK** (the active format) or **Delete color**. Deleting one swatch affects the working palette only. During sampling, right-click retains its save-current-selection behavior.

Exports use the textual, 8-bit sRGB [GIMP Palette format](https://developer.gimp.org/core/standards/gpl/), including `GIMP Palette`, `Name:`, `Columns:`, and RGB entries. Files may be empty palettes. File dialogs and confirmation windows temporarily stop sampling and hide the layer surfaces so the system UI remains accessible; the color and palette windows return in normal pointer mode when the dialog completes or is cancelled.

```sh
~/.local/bin/native-eyedropper --toggle
~/.local/bin/native-eyedropper --status
~/.local/bin/native-eyedropper --show-palette
~/.local/bin/native-eyedropper --show-color '#A785D8'
~/.local/bin/native-eyedropper --quit
```

`--show-palette` opens the saved palette without adding a color, including when it is empty. `--idle` starts the application without enabling sampling. With no arguments, the command toggles sampling. `--status` starts an idle instance if none exists.

## Appearance, language and precision

Open the **Preferences** gear on either floating window. Both gears open the same window. Changes apply immediately:

- **Language:** System, English, Español or Português (Brasil). English is the source language and per-string fallback. Automatic detection honors `LC_ALL`, `LC_MESSAGES`, `LANGUAGE` and `LANG`; C/POSIX resolves to English. Spanish regional locales map to Spanish, and Portuguese locales map to pt-BR. The system file chooser retains the desktop's own language; the application's supplied labels and confirmations are translated.
- **Frosted glass:** Automatic follows COSMIC's window-glass setting, Enabled requests blur explicitly, Disabled uses opaque backgrounds. The active COSMIC background, foreground, dividers and accent are watched for changes, including dark/light switches. Only window backgrounds use alpha; swatches and cursor pixels remain opaque. Header icons use COSMIC's accent-text color while their window has keyboard focus and its muted icon color when inactive; hover/pressed fills also come from the active theme. No global desktop configuration is modified.

The visible **previous/next arrows** in the color window cycle HEX → RGB → HSL → CMYK. During sampling, the keyboard's Left/Right arrows do the same. Copy always uses the active format, including palette context menus. RGB remains the canonical 24-bit value; changing display format never quantizes the selected color or changes `.gpl` exports.

Formats use `#RRGGBB`, `rgb(R, G, B)`, `hsl(H, S%, L%)` and `cmyk(C%, M%, Y%, K%)`. HSL and CMYK have at most one decimal with a locale-independent decimal point. CMYK is a mathematical approximation without an ICC printing profile; the interface displays that limitation whenever CMYK is selected.

The magnifier starts at **4×** every time sampling is enabled. Wheel up increases zoom and wheel down decreases it through 1×/2×/4×/8×/16×, clamping at the ends. Smooth wheel deltas accumulate. A black/white outline marks the central pixel without tinting its interior. Source pixels are copied in output orientation, with edge clamping and nearest-neighbor magnification. The magnifier flips to the other side of the ring near output edges, preserving the sampling hotspot. Leaving sampling hides it and resets zoom to 4×.

Preferences are stored in `$XDG_CONFIG_HOME/okayu-color-picker/settings.json` (normally `~/.config`). Defaults are `language: auto`, `format: HEX`, `glass: auto`. Zoom is deliberately not persisted. Existing selection, palette and position files are retained.

## How it works

`picker.py` owns the GTK application, transparent layer-shell selection surfaces, cursor, clipboard, and color window. A background thread calls `libpixel-capture.so` through ctypes. `pixel_capture.c` connects to Wayland and captures outputs into anonymous shared-memory buffers using the compositor's image-copy protocols. The ring and magnifier are a single cursor image and are not requested as part of capture (`paint_cursors` is disabled). The cursor remains mapped throughout readback; the capture loop never blanks or hides it. Identical cursor images are reused rather than recreated on every sample. On COSMIC, the native capture path uses `zcosmic_workspace_image_capture_source_manager_v1` with the active workspace associated with each output through `ext_workspace_manager_v1`. COSMIC renders this source with its no-cursor renderer rather than copying the final monitor framebuffer. This avoids the observed custom-cursor feedback in output capture while leaving the ring and magnifier continuously visible. Active workspace changes recreate the affected capture session. An output-source fallback remains available on compositors without the COSMIC workspace extension; that path is not validated for cursor exclusion here. Buffers still prefer advertised opaque RGB and sessions never request `paint_cursors`. Output discovery does not pre-fill screenshot buffers. During sampling, application tooltips are disabled so tooltip windows cannot contaminate a pixel selection. They return in normal pointer mode. `pixel_region` copies an odd RGB square centered on exactly the same pixel as `pixel_read`, using integer neighbor steps for all eight output transforms. The caller owns the region buffer; screenshots are never written to disk. `magnifier.py` renders within GDK's advertised cursor size, and `picker_model.py` handles format conversion, validated settings and gettext. `cosmic_style.py` and `libcosmic-effects.so` follow COSMIC colors and attach optional native background effects through public GDK Wayland APIs. Blur uses one continuous rectangular region; COSMIC's version-2 layer corner-radius hint clips the effect and surface together at the same 12-logical-pixel radius as the GTK background. This avoids the horizontal seams produced by per-scanline blur regions. Layer-bound hints are released before hiding, destroying or moving the layer role to another output. Monitor origins associate GTK surfaces with captured outputs; pointer coordinates are normalized to each output. Selection and palette-save commands are serialized, so a rapid left-click followed by a right-click saves the new selection. Pointer events are intercepted before child widgets consume modified clicks or sampling clicks. The global handler receives a `Gdk.Event` union and reads button/modifier values through `get_button()` and `get_state()`; its `.button` member is a structure, not a button number. Close-button events pass through to GTK while sampling.

Cross-output movement uses GTK/Wayland drag-and-drop: a compositor-owned drag icon renders the window at its original pointer hotspot, while transparent drop targets cover each output. The source remains mapped but transparent during the drag. A successful drop records output-local coordinates, then relocates the source after the drag completes. This avoids accumulating coordinate drift from a moving layer surface or interpreting Wayland surface-local coordinates as desktop-global coordinates. Cancelling restores the source and removes drop targets. No privileged input service, polling of global pointer coordinates, or compositor configuration changes are needed. See the GTK documentation for [drag icons](https://docs.gtk.org/gtk3/func.drag_set_icon_surface.html) and [drop handling](https://docs.gtk.org/gtk3/signal.Widget.drag-drop.html).

The application does not save screen images. The last selected HEX value is saved to `$XDG_STATE_HOME/okayu-color-picker/selection.json` (default `~/.local/state`). `palette.json` stores unique RGB colors in insertion order, and `windows.json` stores window positions and output identification. These user data files are not part of this repository. While sampling, screen contents are available in process memory. Selection surfaces temporarily intercept input across outputs; stop sampling to interact normally with other applications. Protected surfaces or compositor restrictions may prevent capture. Physical drag acceptance is recorded separately in [VALIDATION.md](VALIDATION.md); callback tests are not a substitute for it. HDR/color-managed output, rotated displays, hotplugging, and other compositors have not been comprehensively tested. HEX values describe captured 8-bit RGB pixels, not calibrated physical display colors.

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
python3 -m py_compile picker.py picker_model.py magnifier.py cosmic_style.py
python3 -m unittest discover -p "test_*.py"
bash -n install.sh build.sh
```

The original implementation was manually exercised on a three-monitor COSMIC desktop, including exact-color capture checks, live changes, and persistence of the color window after sampling stops. Automated unit tests cover color formatting, exact pixels in both ring halves, palette validation and file round-trips, `.gpl` extension normalization, creation of the Pictures/Palette folder, selection persistence, and click ordering. An opt-in session test briefly displays native windows and a known-color patch:

```sh
EYEDROPPER_WAYLAND_TEST=1 python3 -m unittest test_wayland test_update.ThemeTests -v
```

The independent native-session scenarios also verify the toolbar order, native save-chooser creation/cancellation, filename completion, file loading, invalid-file preservation, context-menu actions, and cancel/confirm cleanup behavior. Each scenario runs in a separate process because GTK/portal state is process-global. The capture scenario verifies Super+click dispatch using real `Gdk.Event` unions (including events on child buttons), active-mode close-button dispatch, independent palette closure/reopening, live screen capture, immediate select-then-save ordering, palette sampling, normal swatch clicks, remembered state, source icon hotspot, and drop placement on each output. It uses simulated drag initiation/drop callbacks; it does **not** prove a physical mouse drag's compositor behavior. For that, manually Super+left-drag both windows across each monitor boundary and verify that the original grab point stays under the cursor until release, including mixed scaling. Cancel a drag with Escape and check the original position. The physical 100%/125%/150% acceptance gate is tracked in VALIDATION.md; it must pass before publishing this candidate as validated. To test manually, display a known solid RGB patch, select it, compare its HEX value, toggle sampling off, and verify that Copy HEX and the close button still work. Repeat on every output and scaling configuration. Verify that the upper ring changes while its lower half stays selected; right-click twice to check deduplication; then stop sampling and click each saved swatch. Actual pointer-drag acceptance should be checked separately from the automated drop-placement checks.

### Translation maintenance

Edit `es.po` or `pt_BR.po` and run `bash build.sh`. Compiled `.mo` catalogs under `locale/` are build artifacts; installation includes them. Catalogs use Python's standard gettext fallback rather than network translation. Tests verify source-message coverage and missing-message English fallback.

The additional update tests exercise color conversion edges, settings persistence, zoom accumulation, cursor geometry and exact center pixels, native region orientation for all eight transforms, a live Gio theme-change notification, language changes without restart, and real capture exclusion of a deliberately contrasting cursor/magnifier across all outputs. A separate live-sampler regression checks that the real capture worker keeps the visible cursor mapped while reading every output, validates the selected RGB and every magnifier pixel against a known background across repeated updates, and restores tooltips on exit. Native GUI tests use independent processes and temporary settings/state.

## License

Original project code is MIT-licensed. Vendored Wayland protocol definitions and generated bindings retain their upstream copyright and license notices; see [THIRD_PARTY.md](THIRD_PARTY.md).
