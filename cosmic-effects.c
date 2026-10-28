/* Native bridge to the compositor's ext-background-effect-v1 protocol.
 * GDK owns the connection and surface commits. Our registry has its own queue.
 * No GTK private structures, global input access or compositor configuration writes.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <wayland-client.h>
#include "ext-background-effect-v1-client.h"
#include "corners.h"

/* Public GDK Wayland APIs, declared with opaque GObject types to avoid a
 * build-time dependency on GTK development headers. */
extern struct wl_display *gdk_wayland_display_get_wl_display(void *display);
extern struct wl_surface *gdk_wayland_window_get_wl_surface(void *window);
extern int gtk_layer_is_layer_window(void *window);
extern struct zwlr_layer_surface_v1 *gtk_layer_get_zwlr_layer_surface_v1(void *window);

struct cf_effect {
    struct ext_background_effect_surface_v1 *blur;
    struct cosmic_corner_radius_layer_v1 *corners;
};

struct cf_context {
    struct wl_display *display;
    struct wl_event_queue *queue;
    struct wl_registry *registry;
    struct wl_compositor *compositor;
    struct ext_background_effect_manager_v1 *manager;
    uint32_t caps;
    struct cosmic_corner_radius_manager_v1 *corners;
};

static void capabilities(void *data, struct ext_background_effect_manager_v1 *manager, uint32_t flags) {
    (void)manager;
    ((struct cf_context *)data)->caps = flags;
}
static const struct ext_background_effect_manager_v1_listener manager_listener = {capabilities};

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    struct cf_context *ctx = data;
    if (!strcmp(interface, "cosmic_corner_radius_manager_v1") && version >= 2)
        ctx->corners = wl_registry_bind(registry, name, &cosmic_corner_radius_manager_v1_interface, 2);
    else if (!strcmp(interface, "wl_compositor"))
        ctx->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
    else if (!strcmp(interface, "ext_background_effect_manager_v1")) {
        ctx->manager = wl_registry_bind(registry, name, &ext_background_effect_manager_v1_interface, 1);
        ext_background_effect_manager_v1_add_listener(ctx->manager, &manager_listener, ctx);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data; (void)registry; (void)name;
}
static const struct wl_registry_listener registry_listener = {global, removed};

void cf_free(struct cf_context *ctx) {
    if (!ctx) return;
    if (ctx->corners) cosmic_corner_radius_manager_v1_destroy(ctx->corners);
    if (ctx->manager) ext_background_effect_manager_v1_destroy(ctx->manager);
    if (ctx->compositor) wl_compositor_destroy(ctx->compositor);
    if (ctx->registry) wl_registry_destroy(ctx->registry);
    if (ctx->queue) wl_event_queue_destroy(ctx->queue);
    free(ctx);
}

struct cf_context *cf_init(void *gdk_display) {
    struct cf_context *ctx = calloc(1, sizeof(*ctx));
    if (!ctx) return NULL;
    ctx->display = gdk_wayland_display_get_wl_display(gdk_display);
    if (!ctx->display) { free(ctx); return NULL; }
    ctx->queue = wl_display_create_queue(ctx->display);
    if (!ctx->queue) { free(ctx); return NULL; }
    void *wrapper = wl_proxy_create_wrapper(ctx->display);
    wl_proxy_set_queue(wrapper, ctx->queue);
    ctx->registry = wl_display_get_registry(wrapper);
    wl_proxy_wrapper_destroy(wrapper);
    wl_registry_add_listener(ctx->registry, &registry_listener, ctx);
    if (wl_display_roundtrip_queue(ctx->display, ctx->queue) < 0 ||
        wl_display_roundtrip_queue(ctx->display, ctx->queue) < 0 ||
        !ctx->compositor || !ctx->manager) {
        cf_free(ctx);
        return NULL;
    }
    return ctx;
}

int cf_supported(struct cf_context *ctx) {
    if (!ctx) return 0;
    wl_display_dispatch_queue_pending(ctx->display, ctx->queue);
    return !!(ctx->caps & EXT_BACKGROUND_EFFECT_MANAGER_V1_CAPABILITY_BLUR);
}

void *cf_attach(struct cf_context *ctx, void *gdk_window, void *gtk_window) {
    if (!ctx || !gdk_window) return NULL;
    struct wl_surface *surface = gdk_wayland_window_get_wl_surface(gdk_window);
    if (!surface) return NULL;
    struct cf_effect *effect = calloc(1, sizeof(*effect));
    if (!effect) return NULL;
    effect->blur = ext_background_effect_manager_v1_get_background_effect(ctx->manager, surface);
    if (ctx->corners && gtk_window && gtk_layer_is_layer_window(gtk_window)) {
        struct zwlr_layer_surface_v1 *layer = gtk_layer_get_zwlr_layer_surface_v1(gtk_window);
        if (layer) effect->corners = cosmic_corner_radius_manager_v1_get_corner_radius_layer(ctx->corners, layer);
    }
    return effect;
}

void *cf_surface(void *gdk_window) {
    return gdk_window ? gdk_wayland_window_get_wl_surface(gdk_window) : NULL;
}

void cf_update(struct cf_context *ctx, void *handle, int width, int height, int radius, int enable) {
    struct cf_effect *effect = handle;
    if (!ctx || !effect || width <= 0 || height <= 0) return;
    int r = radius;
    if (r > width / 2) r = width / 2;
    if (r > height / 2) r = height / 2;
    if (r < 0) r = 0;
    if (effect->corners)
        cosmic_corner_radius_layer_v1_set_radius(effect->corners, r, r, r, r);
    if (!enable || !cf_supported(ctx)) {
        ext_background_effect_surface_v1_set_blur_region(effect->blur, NULL);
    } else {
        struct wl_region *region = wl_compositor_create_region(ctx->compositor);
        /* One continuous blur domain. Per-row rounded regions produce seams
         * when COSMIC processes the region rectangles independently. Corner
         * clipping belongs to the compositor's native layer-corner protocol. */
        wl_region_add(region, 0, 0, width, height);
        ext_background_effect_surface_v1_set_blur_region(effect->blur, region);
        wl_region_destroy(region);
    }
    /* GTK commits the corner hint, effect and buffer together on redraw. */
    wl_display_flush(ctx->display);
}

void cf_detach(void *handle) {
    struct cf_effect *effect = handle;
    if (!effect) return;
    if (effect->corners) cosmic_corner_radius_layer_v1_destroy(effect->corners);
    if (effect->blur) ext_background_effect_surface_v1_destroy(effect->blur);
    free(effect);
}
