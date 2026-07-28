"""Cached, batched overlay drawing for native sketch curves.

Builds GPU batches from :mod:`render_data` and caches them per sketch, keyed by
a cheap change-signature. Batches (and the geometry extraction behind them) are
rebuilt only when the signature changes, so a static or merely-redrawn viewport
costs a signature hash and a few draw calls instead of re-extracting and
re-uploading every element every frame.

Everything of one kind draws in a single per-vertex-color batch -- all points
(as billboarded quads), all solid lines, all dashed lines -- so the draw-call
count stays constant regardless of selection. Only geometry or selection changes
invalidate a batch.
"""

import gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Context

from ..utilities import preferences
from ..utilities.preferences import get_prefs
from ..shaders import Shaders
from ..model.sketch_ref import get_sketches
from . import render_data as rd


# obj_name -> (signature, point_batch, line_batch, dashed_batch)
_cache = {}

# Two triangles covering [-1, 1]^2, for expanding a point into a screen quad.
_QUAD_CORNERS = [
    (-1, -1), (1, -1), (1, 1),
    (-1, -1), (1, 1), (-1, 1),
]


def _theme_signature(ts):
    return tuple(
        tuple(getattr(ts, name))
        for name in (
            "default", "highlight", "selected", "selected_highlight",
            "fixed", "inactive", "inactive_selected",
        )
    )


def _build_batches(data):
    """Turn extracted buckets into a *few* GPU batches with per-vertex color.

    Everything of one kind draws in a single batch/draw call regardless of
    selection: all points, all solid lines, all dashed (construction) lines.
    This keeps the draw-call count constant when selection changes -- adding a
    selected-color bucket no longer adds a draw call, which is what exhausted the
    Vulkan descriptor pool (``OUT_OF_POOL_MEMORY``) and dropped the last call.
    """
    # Points are drawn as billboarded quads (2 tris) so per-vertex color works
    # (GL_POINTS didn't apply it on the Vulkan backend). Each point contributes
    # 6 vertices sharing the same center/color; the per-point size factor is
    # baked into `corner` so hovered/selected points draw bigger in the same
    # batch.
    pverts, pcols, pcorners = [], [], []
    for color, entries in data.point_buckets.items():
        for pos, psize in entries:
            pverts += [pos] * 6
            pcols += [color] * 6
            pcorners += [(cx * psize, cy * psize) for cx, cy in _QUAD_CORNERS]
    point_batch = (
        batch_for_shader(Shaders.point_sprite_color_3d(), "TRIS",
                         {"pos": pverts, "color": pcols, "corner": pcorners})
        if pverts else None
    )

    sverts, scols, dverts, dcols = [], [], [], []
    for (construction, color), verts in data.line_buckets.items():
        if not verts:
            continue
        if construction:
            dverts += verts
            dcols += [color] * len(verts)
        else:
            sverts += verts
            scols += [color] * len(verts)
    line_batch = (
        batch_for_shader(Shaders.polyline_flat_color_3d(), "LINES",
                         {"pos": sverts, "color": scols})
        if sverts else None
    )
    dashed_batch = (
        batch_for_shader(Shaders.dashed_flat_color_line_3d(), "LINES",
                         {"pos": dverts, "color": dcols})
        if dverts else None
    )
    return point_batch, line_batch, dashed_batch


def _draw_points(batch, scale, is_active, region):
    if batch is None:
        return
    # `size` is the on-screen point diameter in pixels. Base points draw at 0.75x
    # the legacy 5px/3px sizes; hovered/selected points scale up further via the
    # per-point factor baked into `corner`.
    size = (5 if is_active else 3) * scale * 0.75
    shader = Shaders.point_sprite_color_3d()
    shader.bind()
    shader.uniform_float("size", size)
    shader.uniform_float("viewportSize", (region.width, region.height))
    gpu.state.blend_set("ALPHA")
    batch.draw(shader)
    gpu.shader.unbind()
    gpu.state.blend_set("NONE")


def _draw_lines(line_batch, dashed_batch, scale, region):
    if line_batch is not None:
        line_width = 2 * scale
        shader = Shaders.polyline_flat_color_3d()
        shader.bind()
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(line_width)
        shader.uniform_float("lineWidth", line_width)
        shader.uniform_float("viewportSize", (region.width, region.height))
        line_batch.draw(shader)
        gpu.shader.unbind()
        gpu.state.line_width_set(1)
        gpu.state.blend_set("NONE")

    if dashed_batch is not None:
        shader = Shaders.dashed_flat_color_line_3d()
        shader.bind()
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(1.5 * scale)
        shader.uniform_bool("dashed", (True,))
        shader.uniform_float("dash_width", 0.05)
        shader.uniform_float("dash_factor", 0.3)
        dashed_batch.draw(shader)
        gpu.shader.unbind()
        gpu.state.line_width_set(1)
        gpu.state.blend_set("NONE")


def draw(context: Context):
    """Draw the overlay for every visible sketch, reusing cached batches."""
    if context.scene.sketcher.active_sketch_object is None:
        return

    ts = get_prefs().theme_settings.entity
    theme_sig = _theme_signature(ts)
    scale = preferences.get_scale()
    active_obj = context.scene.sketcher.active_sketch_object
    region = context.region

    seen = set()
    for sketch in get_sketches(context):
        if not sketch.is_visible(context):
            continue
        obj = sketch.target_object
        if not obj or not obj.data or len(obj.data.curves) == 0:
            continue

        name = obj.name
        seen.add(name)
        is_active = obj == active_obj
        sig = rd.overlay_signature(sketch, is_active, theme_sig)

        cached = _cache.get(name)
        if cached is None or cached[0] != sig:
            data = rd.build(sketch, ts, is_active)
            point_batch, line_batch, dashed_batch = _build_batches(data)
            _cache[name] = (sig, point_batch, line_batch, dashed_batch)
        else:
            _, point_batch, line_batch, dashed_batch = cached

        _draw_lines(line_batch, dashed_batch, scale, region)
        _draw_points(point_batch, scale, is_active, region)

    # Drop cache entries for sketches that no longer exist / are hidden.
    for stale in [n for n in _cache if n not in seen]:
        del _cache[stale]


def invalidate():
    """Force a full rebuild on the next draw (e.g. on unregister/file load)."""
    _cache.clear()
