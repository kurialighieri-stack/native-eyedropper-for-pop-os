"""Draw a pixel magnifier as part of a cursor, never as a captured surface."""
import array
import cairo

PATCH_SIDE = 145
VIEW = 144


def render_cursor(ring, pixels=None, zoom=4, position=(.5, .5), max_size=(256, 256)):
    if max_size[0] < 72 or max_size[1] < 72:
        scale = max(.01, min(max_size[0] / 72, max_size[1] / 72))
        width, height = max(1, int(72 * scale)), max(1, int(72 * scale))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        cr.scale(scale, scale)
        cr.set_source_surface(ring, 0, 0)
        cr.paint()
        return surface, (min(width - 1, int(36 * scale)), min(height - 1, int(36 * scale)))
    if pixels is None:
        return ring, (36, 36)
    # Fit the magnifier viewport, preserving exact integer zoom rather than scaling it.
    width = min(VIEW, max_size[0] - 84)
    height = min(VIEW, max_size[1] - 20)
    if width < 16 or height < 16:
        return ring, (36, 36)
    left, top = position[0] > .65, position[1] > .65
    rx = width + 10 if left else 0
    mx = 0 if left else 80
    ry = max(0, height + 20 - 72) if top else 0
    my = 0
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width + 82, max(height + 20, 72))
    cr = cairo.Context(surface)
    cr.set_source_surface(ring, rx, ry)
    cr.paint()
    cr.rectangle(mx, my, width, height)
    cr.set_source_rgb(.06, .05, .08)
    cr.fill()
    data = array.array('I', pixels)
    image = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_RGB24, PATCH_SIDE, PATCH_SIDE, PATCH_SIDE * 4)
    ox, oy = mx + width // 2 - zoom // 2, my + height // 2 - zoom // 2
    cr.save()
    cr.rectangle(mx, my, width, height)
    cr.clip()
    cr.translate(ox, oy)
    cr.scale(zoom, zoom)
    cr.set_source_surface(image, -(PATCH_SIDE // 2), -(PATCH_SIDE // 2))
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()
    # Outlines sit outside the central pixel, leaving its RGB interior untouched.
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    for color, inset in [((0, 0, 0), 2), ((1, 1, 1), 1)]:
        cr.set_source_rgb(*color)
        cr.set_line_width(1)
        cr.rectangle(ox - inset, oy - inset, zoom + inset * 2, zoom + inset * 2)
        cr.stroke()
    cr.set_source_rgb(.03, .02, .04)
    cr.rectangle(mx, height, width, 20)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.select_font_face('sans-serif')
    cr.set_font_size(12)
    cr.move_to(mx + 5, height + 15)
    cr.show_text(f'{zoom}×')
    return surface, (rx + 36, ry + 36)
