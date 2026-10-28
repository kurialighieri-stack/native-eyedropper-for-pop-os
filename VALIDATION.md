# Version 0.2.0 acceptance

Updated: 2026-10-28. This development snapshot is installed locally and published with the current automated results. It is not a physically validated release; the manual checks below remain pending.

## Automated results

- 16 unit/native-buffer tests pass (including a compiled C test of all eight transforms, region center agreement, color conversions, locale catalogs/fallback, settings, zoom and exact cursor pixels).
- Six native Wayland scenarios pass: native keyboard-focus/header-color transitions with wire-level continuous-blur/corner-hint checks; continuously visible-cursor live sampling with repeated magnifier updates; existing palette/file/confirmation behavior; dispatch and placements; live preferences/language/format/zoom; and real capture excluding a contrasting ring/magnifier on every connected output.
- One COSMIC theme integration test passes: live Gio file-change detection, accent/theme reload, glass override and opaque fallback.
- Native build and gettext catalog checks pass. User state is outside the source repository.

## Physical acceptance — awaiting user observation

These tests cannot be certified by synthetic GDK events or drag callbacks. For each scale, test both floating windows, both Super+left and unmodified middle-button drag, crossing output boundaries, matching the grab hotspot, release placement, and Escape cancellation. Include a mixed-scale boundary.

| Display scale | Super+left | Middle button | Cross-output hotspot / placement |
| --- | --- | --- | --- |
| 100% | Pending | Pending | Pending |
| 125% | Pending | Pending | Pending |
| 150% | Pending | Pending | Pending |

The matrix records physical observations only. Automated callbacks cannot establish a pass here. Pending means the configuration has not yet been verified; it does not mean a failed test.

## Cursor-feedback and flicker regressions

User testing reported feedback of the custom cursor into live sampling. An initial blank-cursor guard caused unacceptable visible flickering and has been removed. A second user screenshot confirmed output capture still included the custom cursor. The current candidate therefore uses COSMIC active-workspace capture, which renders the scene without cursors, instead of its final-output framebuffer path. It keeps the pointer/magnifier mapped during every readback, reuses unchanged cursor objects, suppresses application tooltips while sampling, and prefers an advertised opaque RGB capture buffer while retaining protocol cursor exclusion.

Automated known-background tests verify picked RGB and the full magnifier patch during repeated updates on all outputs, require a non-blank cursor throughout readback, and check that unchanged images retain the same cursor object. This is not physical-pointer acceptance: confirmation that the user's feedback and flicker are both gone is still required. Tests now assert that the actual native session uses the COSMIC workspace backend on all outputs and cover output/group mapping, inactive/removed workspaces, palette sampling, and RGB region fidelity. Physical drag acceptance also remains pending.

## Window appearance regression

User screenshots showed scanline seams at the top/bottom of rounded blur regions and unchanging header-icon colors. The effect now submits one rectangle, with COSMIC's native layer-corner hint supplying clipping at the same radius as GTK. A native-session test reads the actual Wayland request stream to require a single rectangle for every blur region and the corner-radius request. It then switches real keyboard focus between the two windows and verifies rendered GTK icon colors against the active theme's accent-text and muted-icon values. Existing native tests also cover hide/destroy/remap lifecycle without protocol errors.
