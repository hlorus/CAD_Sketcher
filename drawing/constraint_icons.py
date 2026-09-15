"""Batched constraint-icon rendering.

The constraint gizmos used to draw their icon in each gizmo's ``draw()`` -- one
textured (sampler-bound) draw per constraint, which on the Vulkan backend
exhausted the descriptor pool (``VK_ERROR_OUT_OF_POOL_MEMORY``) once a sketch had
many constraints. Here every geometric constraint's icon is drawn in a *single*
batched call from one texture atlas, so there is exactly one sampler bind.

Picking an icon (hover highlight, click for the context menu) is answered from
the same layout by one gizmo for all icons (see ``hit_test``), instead of a gizmo
per constraint.
"""

import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .. import icon_manager
from ..model.sketch_ref import get_active_sketch
from ..shaders import Shaders
from ..utilities.preferences import get_prefs
from . import frame_cache, selection


def _world_entries(context, sketch):
    """(world position, stack index, constraint type, color, index) per icon.

    Everything about an icon except where the view puts it, mirroring the gizmo
    group's placement and stacking.
    """
    from ..gizmos.utilities import get_constraint_color_type
    from ..model.base_constraint import DimensionalConstraint

    # Group constraints by the curve their marker sits on (for stacking offset).
    mapping = {}
    index_of = {}
    for coll in sketch.constraints.get_lists():
        for index, c in enumerate(coll):
            if isinstance(c, DimensionalConstraint) or not c.visible:
                continue
            index_of[c.as_pointer()] = index
            for cid in c.curve_id_placements():
                mapping.setdefault(cid, []).append(c)

    entries = []
    for cid, constrs in mapping.items():
        for i, c in enumerate(constrs):
            world = None
            if hasattr(c, "marker_position"):
                try:
                    world = c.marker_position(sketch)
                except Exception:
                    world = None
            if world is None:
                world = frame_cache.curve_placement(sketch, cid)
            if world is None:
                continue

            is_highlight = c == selection.highlight_constraint
            color = frame_cache.constraint_color(
                get_constraint_color_type(c), is_highlight
            )
            entries.append(
                (tuple(world[:3]), i, c.type, tuple(color), index_of[c.as_pointer()])
            )
    return entries


def _screen_centers(context, positions, stack):
    """Icon centers in region pixels, or None for icons behind the view.

    The per-icon math of location_3d_to_region_2d and get_scale_from_pos, done
    for all icons at once so a view change doesn't loop over constraints.
    """
    rv3d = context.region_data
    region = context.region
    ui_scale = context.preferences.system.ui_scale
    size = get_prefs().gizmo_scale * ui_scale

    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    co4 = np.hstack((positions, np.ones((len(positions), 1))))
    clip = co4 @ persp.T
    w = clip[:, 3]
    visible = w > 0.0
    safe_w = np.where(visible, w, 1.0)
    half = np.array((region.width / 2.0, region.height / 2.0))
    pos = half + half * (clip[:, :2] / safe_w[:, None])

    if rv3d.view_perspective == "ORTHO":
        scale = np.full(len(positions), rv3d.view_distance)
    else:
        # get_scale_from_pos is given the 2D position here, as the gizmo does.
        scale = pos[:, 0] * persp[3, 0] + pos[:, 1] * persp[3, 1] + persp[3, 3]
    scale_3d = np.maximum(1.0, scale / 500.0)

    centers = pos + (size / scale_3d)[:, None]
    centers[:, 0] += size * stack * ui_scale
    return centers, visible, size


# The last icon batch and the key it was built for. Every icon's position and
# color is a function of the key, so an unchanged key reuses the batch.
_icon_cache = {
    "key": None,
    "batch": None,
    "layout_key": None,
    "entries": None,
    # Screen centers of the drawn icons and the entries they belong to.
    "hits": None,
}


def _layout_key(context, sketch):
    """Everything the icons depend on except the view, cheap enough to check every frame.

    Rebuilding the batch walked every constraint in Python (placement, projection,
    stacking, color) on every redraw, a cost that grew with each constraint. While
    drawing, a preview doesn't move the geometry existing constraints sit on, so
    positions are fingerprinted only for the curves that carry a constraint.
    """
    from ..model.base_constraint import DimensionalConstraint
    from ..utilities.curve_data import get_curve_index

    cd = sketch.target_object.data
    constraints = sketch.constraints
    per_constraint = []
    referenced = set()
    for c in constraints.all:
        if isinstance(c, DimensionalConstraint):
            continue
        ids = tuple(c.curve_id_placements())
        per_constraint.append((c.type, ids, c.visible, c.failed))
        referenced.update(ids)

    positions = b""
    if referenced and len(cd.points):
        offsets = np.empty(len(cd.curves) + 1, dtype=np.int32)
        cd.curve_offset_data.foreach_get("value", offsets)
        co = np.empty(len(cd.points) * 3, dtype=np.float32)
        cd.points.foreach_get("position", co)
        co = co.reshape(-1, 3)
        chunks = []
        for cid in sorted(referenced):
            idx = get_curve_index(sketch, cid)
            if idx is None or idx >= len(offsets) - 1:
                chunks.append(np.full((1, 3), np.nan, dtype=np.float32))
            else:
                chunks.append(co[offsets[idx] : offsets[idx + 1]])
        positions = np.concatenate(chunks).tobytes() if chunks else b""

    highlight = selection.highlight_constraint
    highlight_key = (
        (highlight.type, constraints.get_index(highlight)) if highlight else None
    )
    theme = get_prefs().theme_settings.constraint
    return (
        sketch.target_object.as_pointer(),
        tuple(per_constraint),
        hash(positions),
        tuple(tuple(row) for row in sketch.target_object.matrix_world),
        highlight_key,
        tuple(
            tuple(getattr(theme, name))
            for name in (
                "default",
                "highlight",
                "failed",
                "failed_highlight",
                "reference",
                "reference_highlight",
            )
        ),
    )


def _view_key(context, atlas, uvs):
    """Where the view puts the icons, and the atlas they are drawn from."""
    rv3d = context.region_data
    region = context.region
    return (
        tuple(tuple(row) for row in rv3d.perspective_matrix),
        (region.width, region.height),
        context.preferences.system.ui_scale,
        get_prefs().gizmo_scale,
        # The batch bakes the atlas UVs in, so a rebuilt atlas must rebuild it.
        id(atlas),
        id(uvs),
    )


def _icon_key(context, sketch, atlas, uvs):
    """Everything the icon batch depends on."""
    return (_layout_key(context, sketch), _view_key(context, atlas, uvs))


def invalidate():
    """Drop the cached icon batch (e.g. on file load)."""
    _icon_cache.update(key=None, batch=None, layout_key=None, entries=None, hits=None)


def targets():
    """(constraint type, index) of each laid out icon, in hit-test order."""
    entries = _icon_cache["entries"] or ()
    return tuple((e[2], e[4]) for e in entries)


def hit_test(location):
    """Index into ``targets()`` of the icon under a region location, or None.

    Uses the icons as last drawn, so the hit area is always where the icon is.
    """
    hits = _icon_cache["hits"]
    if not hits:
        return None
    centers, entry_indices, radius = hits
    if not len(centers):
        return None
    d2 = ((centers - np.asarray(location[:2], dtype=np.float64)) ** 2).sum(axis=1)
    nearest = int(np.argmin(d2))
    if d2[nearest] >= radius * radius:
        return None
    return int(entry_indices[nearest])


def draw():
    """POST_PIXEL handler: draw every constraint icon in one atlas-batched call."""
    import bpy

    context = bpy.context
    if context.scene.sketcher.active_sketch_object is None:
        return
    sketch = get_active_sketch(context)
    if not sketch or context.region_data is None:
        return

    atlas, uvs = icon_manager.get_atlas()
    if atlas is None or not uvs:
        return

    shader = Shaders.atlas_icon_2d()
    key = _icon_key(context, sketch, atlas, uvs)
    if _icon_cache["key"] == key:
        batch = _icon_cache["batch"]
    else:
        # Walking the constraints is only needed when they or their geometry
        # changed; a view change just moves the icons already laid out.
        if _icon_cache["layout_key"] != key[0]:
            _icon_cache["entries"] = _world_entries(context, sketch)
            _icon_cache["layout_key"] = key[0]
        batch, hits = _build_batch(context, _icon_cache["entries"], shader, uvs)
        _icon_cache["hits"] = hits
        _icon_cache["key"] = key
        _icon_cache["batch"] = batch

    if batch is None:
        return
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_sampler("image", atlas)
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def _build_batch(context, entries, shader, uvs):
    """The icon batch, and (centers, entry indices, radius) of the drawn icons."""
    drawn = [i for i, e in enumerate(entries) if e[2] in uvs]
    if not drawn:
        return None, None
    positions = np.array([entries[i][0] for i in drawn], dtype=np.float64)
    stack = np.array([entries[i][1] for i in drawn], dtype=np.float64)
    centers, visible, size = _screen_centers(context, positions, stack)
    keep = np.flatnonzero(visible)
    if not keep.size:
        return None, None

    h = size / 2.0
    corners = np.array(
        ((-h, -h), (h, -h), (h, h), (-h, -h), (h, h), (-h, h)), dtype=np.float32
    )
    verts = (centers[keep, None, :] + corners[None, :, :]).reshape(-1, 2)
    texco = []
    colors = []
    for k in keep.tolist():
        entry = entries[drawn[k]]
        u0, v0, u1, v1 = uvs[entry[2]]
        texco += [(u0, v0), (u1, v0), (u1, v1), (u0, v0), (u1, v1), (u0, v1)]
        colors += [entry[3]] * 6
    batch = batch_for_shader(
        shader,
        "TRIS",
        {"pos": verts.astype(np.float32), "texCoord": texco, "color": colors},
    )
    # The gizmo's hit circle had the icon size as its radius.
    hits = (centers[keep], np.array(drawn)[keep], size)
    return batch, hits
