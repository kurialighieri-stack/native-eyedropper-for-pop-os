# Third-party components

The XML protocol definitions in the repository were obtained from the [Wayland protocols mirror](https://github.com/wayland-mirror/wayland-protocols):

- `staging/ext-image-copy-capture/ext-image-copy-capture-v1.xml`
- `staging/ext-image-capture-source/ext-image-capture-source-v1.xml`
- `staging/ext-foreign-toplevel-list/ext-foreign-toplevel-list-v1.xml` (stored as `foreign.xml`)

Their complete copyright and permissive license notices remain in each XML file and generated binding. `capture.c/.h`, `source.c/.h`, and `foreign.c` were generated with wayland-scanner. The third-party terms apply to those components independently of the project's original MIT-licensed code. Regeneration requires a compatible wayland-scanner; normal builds use the included generated files.

GTK, PyGObject, Cairo, GtkLayerShell and libwayland are system dependencies, not bundled binaries. Consult their distributions for their respective licenses.
