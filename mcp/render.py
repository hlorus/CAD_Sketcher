"""Render a sketch square-on to its plane, off screen.

Drawn into an offscreen buffer rather than by pointing the user's viewport at the
sketch: the agent gets a deterministic, framed view of what it asked about, and
nothing moves on the user's desk. CAD Sketcher's overlay draws into the offscreen
pass like any other viewport draw, so constraints and dimensions come out too.
"""

import os
import tempfile
from typing import Tuple

import bpy
import gpu
import numpy as np
from mathutils import Matrix, Vector

from ..model.curve_ref import curve_ref
from ..model.sketch_ref import Sketch
from ..utilities.curve_data import read_curve_id_list

# Keep some plane visible around the geometry. A sketch with nothing in it, or
# with everything at one spot, has no extent of its own to frame, so it gets an
# arbitrary but sane one.
_MARGIN = 1.25
_EMPTY_EXTENT = 0.1


class RenderUnavailable(Exception):
    """The render could not be made, with a reason worth telling the agent."""


def _bounds(sketch: Sketch) -> Tuple[Vector, float]:
    """The centre and half-extent of a sketch's geometry, in sketch-local space."""
    curve_data = sketch.target_object.data
    lo = Vector((float("inf"), float("inf")))
    hi = Vector((float("-inf"), float("-inf")))

    for curve_id in read_curve_id_list(curve_data):
        if not curve_id:
            continue
        ref = curve_ref(sketch, curve_id)
        if ref.is_point():
            points = [ref.co]
        elif ref.is_circle() or ref.is_arc():
            center = ref.ct.co if ref.ct else Vector((0, 0))
            radius = ref.radius
            points = [
                center + Vector((radius, radius)),
                center - Vector((radius, radius)),
            ]
        else:
            # A segment's extent is its endpoints, and those are point curves in
            # this same sketch, so they are measured on their own pass.
            continue
        for point in points:
            lo.x, lo.y = min(lo.x, point.x), min(lo.y, point.y)
            hi.x, hi.y = max(hi.x, point.x), max(hi.y, point.y)

    if lo.x == float("inf"):
        return Vector((0.0, 0.0)), _EMPTY_EXTENT

    center = (lo + hi) / 2
    half = max((hi - lo).x, (hi - lo).y) / 2 * _MARGIN
    # Only a sketch with no extent at all falls back; a floor above that would
    # zoom out past small work, which is most of it in metres.
    return center, half if half > 1e-6 else _EMPTY_EXTENT


def _ortho_projection(half_extent: float, near: float, far: float) -> Matrix:
    """A square orthographic projection matrix."""
    depth = far - near
    return Matrix(
        (
            (1.0 / half_extent, 0.0, 0.0, 0.0),
            (0.0, 1.0 / half_extent, 0.0, 0.0),
            (0.0, 0.0, -2.0 / depth, -(far + near) / depth),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def _view_matrix(sketch: Sketch, center: Vector, distance: float) -> Matrix:
    """World-to-view for a camera on the sketch's normal, looking at ``center``."""
    plane = sketch.world_matrix
    # The plane's own axes, without whatever scale it carries.
    rotation = plane.to_quaternion().to_matrix().to_4x4()
    eye = plane @ Vector((center.x, center.y, distance))
    frame = rotation.copy()
    frame.translation = eye
    return frame.inverted()


def sketch_png(context, sketch: Sketch, size: int) -> bytes:
    """PNG bytes of ``sketch`` seen square-on, framed on its geometry."""
    space_data, region = _viewport(context)

    # What the picture shows is the evaluated geometry, so an edit made in the
    # same breath has to reach the depsgraph before it can be looked at.
    context.view_layer.update()

    center, half_extent = _bounds(sketch)
    distance = max(half_extent * 4.0, 1.0)
    view_matrix = _view_matrix(sketch, center, distance)
    projection = _ortho_projection(half_extent, 0.01, distance * 4.0)

    offscreen = gpu.types.GPUOffScreen(size, size)
    try:
        offscreen.draw_view3d(
            context.scene,
            context.view_layer,
            space_data,
            region,
            view_matrix,
            projection,
            do_color_management=True,
        )
        with offscreen.bind():
            buffer = gpu.state.active_framebuffer_get().read_color(
                0, 0, size, size, 4, 0, "UBYTE"
            )
            buffer.dimensions = size * size * 4
    except (RuntimeError, SystemError) as e:
        raise RenderUnavailable(f"Blender could not render the sketch: {e}") from e
    finally:
        offscreen.free()

    return _encode_png(buffer, size)


def _viewport(context):
    """A 3D viewport's space and window region to borrow the draw setup from."""
    for window in getattr(context.window_manager, "windows", ()):
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return area.spaces.active, region
    raise RenderUnavailable(
        "Rendering needs an open 3D viewport, and this Blender has none "
        "(it is running without a window)."
    )


def _encode_png(buffer, size: int) -> bytes:
    """Encode a read framebuffer as PNG, via Blender's own image writer."""
    image = bpy.data.images.new("slvs_mcp_render", size, size, alpha=True)
    path = os.path.join(tempfile.gettempdir(), f"slvs_mcp_{os.getpid()}.png")
    try:
        pixels = np.asarray(buffer, dtype=np.uint8).astype(np.float32) / 255.0
        image.pixels.foreach_set(pixels)
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
        with open(path, "rb") as handle:
            return handle.read()
    finally:
        bpy.data.images.remove(image)
        if os.path.exists(path):
            os.remove(path)
