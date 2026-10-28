# Third-party components

The XML protocol definitions in the repository were obtained from the [Wayland protocols mirror](https://github.com/wayland-mirror/wayland-protocols):

- `staging/ext-image-copy-capture/ext-image-copy-capture-v1.xml`
- `staging/ext-image-capture-source/ext-image-capture-source-v1.xml`
- `staging/ext-background-effect/ext-background-effect-v1.xml` and its generated `ext-background-effect-v1-client.h` / `ext-background-effect-v1-protocol.c` bindings
- `staging/ext-foreign-toplevel-list/ext-foreign-toplevel-list-v1.xml` (stored as `foreign.xml`)

Their complete copyright and permissive license notices remain in each XML file and generated binding. `capture.c/.h`, `source.c/.h`, and `foreign.c` were generated with wayland-scanner. The third-party terms apply to those components independently of the project's original MIT-licensed code. Regeneration requires a compatible wayland-scanner; normal builds use the included generated files.

GTK, PyGObject, Cairo, GtkLayerShell and libwayland are system dependencies, not bundled binaries. Consult their distributions for their respective licenses.

The COSMIC effects bridge and theme adapter were adapted from the same user-owned desktop integration, using public GDK Wayland APIs. Their original project code is covered by this repository's MIT license. The vendored background-effect XML and bindings retain the upstream copyright notices.

Additional capture protocols:

- `ext-workspace-v1.xml`, with generated `workspace.c` / `workspace.h`, from the staging ext-workspace protocol in wayland-protocols.
- `cosmic-image-capture-source-v1.xml`, with generated `cosmic-source.c` / `cosmic-source.h`, from [System76 cosmic-protocols](https://github.com/pop-os/cosmic-protocols/blob/master/unstable/cosmic-image-capture-source-unstable-v1.xml). Copyright © 2025 System76; its complete permissive license is retained in the XML and generated sources.

- `cosmic-corner-radius-v1.xml`, with generated `corners.c` / `corners.h`, from [System76 cosmic-protocols](https://github.com/pop-os/cosmic-protocols/blob/master/unstable/cosmic-corner-radius-unstable-v1.xml). Copyright © 2024 System76; the complete permissive notice is retained. References to xdg-shell and wlr-layer-shell interface descriptions are provided by the existing gtk-layer-shell runtime.
