"""Batched constraint-icon rendering.

The constraint gizmos used to draw their icon in each gizmo's ``draw()`` -- one
textured (sampler-bound) draw per constraint, which on the Vulkan backend
exhausted the descriptor pool (``VK_ERROR_OUT_OF_POOL_MEMORY``) once a sketch had
many constraints. Here every geometric constraint's icon is drawn in a *single*
batched call from one texture atlas, so there is exactly one sampler bind.

Picking an icon (hover highlight, click for the context menu) is answered from
the same layout by one gizmo for all icons (see ``pick``), instead of a gizmo per
constraint.

With many constraints the icons are grouped (see ``_arrange``): the constraints
on one element, and optionally on elements close together on screen, share one
icon with a count badge. A group fans out into its individual icons while the
cursor is over it, or while its geometry is hovered.
"""

import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .. import icon_manager
from ..model.sketch_ref import get_active_sketch
from ..shaders import Shaders
from ..utilities.preferences import get_prefs
from . import frame_cache, selection

# Fields of a laid out icon (see _world_entries).
WORLD, STACK, TYPE, COLOR, INDEX, ANCHOR, PRIORITY = range(7)


def _world_entries(context, sketch):
    """One tuple per icon, indexed by the field constants above.

    The world position, stack index on its element, constraint type, color,
    constraint index, the element the icon sits on (``ANCHOR``), and how much its
    color should stand out in a group.
    Everything about an icon except where the view puts it.
    """
    from ..gizmos.utilities import Color, get_constraint_color_type
    from ..model.base_constraint import DimensionalConstraint

    # A group takes the color that stands out most: highlighted, then failed,
    # then reference.
    priorities = {Color.Failed: 2, Color.Reference: 1}

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
            color_type = get_constraint_color_type(c)
            color = frame_cache.constraint_color(color_type, is_highlight)
            priority = 3 if is_highlight else priorities.get(color_type, 0)
            entries.append(
                (
                    tuple(world[:3]),
                    i,
                    c.type,
                    tuple(color),
                    index_of[c.as_pointer()],
                    cid,
                    priority,
                )
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
    # Elements that have icons on them.
    "anchors": None,
    # Per-icon arrays of the layout (see _prepare), and the atlas UVs they're for.
    "prepared": None,
    "prepared_uvs": None,
    # What was drawn, for picking (see _arrange).
    "hits": None,
}

# The group the cursor is over, kept expanded while the cursor stays on it.
_hover = {"group": None}


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
    _icon_cache.update(
        key=None,
        batch=None,
        layout_key=None,
        entries=None,
        anchors=None,
        prepared=None,
        prepared_uvs=None,
        hits=None,
    )
    _hover["group"] = None


def targets():
    """(constraint type, index) of each laid out icon, in part order."""
    entries = _icon_cache["entries"] or ()
    return tuple((e[TYPE], e[INDEX]) for e in entries)


def pick(location):
    """The icon under a region location, updating which group is expanded.

    Returns ``(part, changed)``: the index into ``targets()`` of the individual
    icon under the cursor (None over a group or empty space), and whether the
    expanded group changed, so the caller can redraw.
    """
    hits = _icon_cache["hits"]
    if not hits:
        return None, _set_hover(None)
    point = np.asarray(location[:2], dtype=np.float64)
    radius = hits["radius"]

    part = _nearest(hits["icon_centers"], point, radius)
    if part is not None:
        return int(hits["icon_entries"][part]), False

    # Moving within the fanned out group keeps it open, so its icons are reachable.
    rect = hits["hover_rect"]
    if rect is not None and np.all(point >= rect[0]) and np.all(point <= rect[1]):
        return None, False

    group = _nearest(hits["group_centers"], point, radius)
    return None, _set_hover(hits["group_keys"][group] if group is not None else None)


def _nearest(centers, point, radius):
    if not len(centers):
        return None
    d2 = ((centers - point) ** 2).sum(axis=1)
    nearest = int(np.argmin(d2))
    return nearest if d2[nearest] < radius * radius else None


def _set_hover(group):
    changed = _hover["group"] != group
    _hover["group"] = group
    return changed


def _expanded_elements():
    """Elements whose icons open because the element is hovered.

    Only the icons sitting on the element itself open, not those of the other
    elements its constraints refer to.
    """
    anchors = _icon_cache["anchors"] or frozenset()
    hover = selection.hover
    return frozenset((hover,)) if hover and hover in anchors else frozenset()


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
    layout_key = _layout_key(context, sketch)
    if _icon_cache["layout_key"] != layout_key:
        # Walking the constraints is only needed when they or their geometry
        # changed; a view change just moves the icons already laid out.
        entries = _world_entries(context, sketch)
        _icon_cache.update(
            entries=entries,
            anchors=frozenset(entry[ANCHOR] for entry in entries),
            layout_key=layout_key,
            prepared=None,
        )
    if _icon_cache["prepared"] is None or _icon_cache["prepared_uvs"] is not uvs:
        _icon_cache["prepared"] = _prepare(_icon_cache["entries"], uvs)
        _icon_cache["prepared_uvs"] = uvs

    mode = get_prefs().constraint_icon_grouping
    expanded = _expanded_elements()
    key = (
        layout_key,
        _view_key(context, atlas, uvs),
        mode,
        expanded,
        _hover["group"],
    )
    if _icon_cache["key"] == key:
        batch = _icon_cache["batch"]
    else:
        batch, hits = _build_batch(
            context, _icon_cache["prepared"], shader, uvs, mode, expanded
        )
        _icon_cache.update(hits=hits, key=key, batch=batch)

    if batch is None:
        return
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_sampler("image", atlas)
    batch.draw(shader)
    _draw_counts(_icon_cache["hits"])
    gpu.state.blend_set("NONE")


# Count badge, relative to the icon size: its radius, and where it sits.
_BADGE_RADIUS = 0.42
_BADGE_OFFSET = 0.5
_BADGE_COLOR = (0.08, 0.08, 0.08, 0.9)
_BADGE_CELLS = ("BADGE",)
# The count's font size relative to the badge radius, and the smallest used.
_COUNT_SIZE = 1.5
_COUNT_MIN_SIZE = 8.0


def _prepare(entries, uvs):
    """Per-icon arrays for the icons that have a texture, and their elements.

    Computed once per layout, so grouping on a view change is array operations
    only.
    """
    drawn = [i for i, e in enumerate(entries) if e[TYPE] in uvs]
    names = sorted({entries[i][TYPE] for i in drawn}) + list(_BADGE_CELLS)
    code_of = {name: code for code, name in enumerate(names)}
    element_of = {}
    element = np.empty(len(drawn), dtype=np.int64)
    for k, i in enumerate(drawn):
        element[k] = element_of.setdefault(entries[i][ANCHOR], len(element_of))
    return {
        "entries": np.array(drawn, dtype=np.int64),
        "positions": np.array(
            [entries[i][WORLD] for i in drawn], dtype=np.float64
        ).reshape(-1, 3),
        "stack": np.array([entries[i][STACK] for i in drawn], dtype=np.float64),
        "codes": np.array([code_of[entries[i][TYPE]] for i in drawn], dtype=np.int64),
        "colors": np.array(
            [entries[i][COLOR] for i in drawn], dtype=np.float32
        ).reshape(-1, 4),
        "priority": np.array([entries[i][PRIORITY] for i in drawn], dtype=np.int64),
        "element": element,
        "element_names": list(element_of),
        "element_index": element_of,
        "names": names,
        "code_of": code_of,
    }


def _arrange(prepared, centers, visible, size, stack_step, mode, expanded):
    """Which quads to draw and what can be picked, after grouping the icons.

    ``centers``/``visible`` are the stacked screen positions of the prepared
    icons. Icons group by the element they sit on; with ``mode`` ``NEARBY``
    elements whose first icons are about an icon apart on screen merge too. A group
    draws as one icon with a count badge unless it has a single icon, grouping is
    ``OFF``, one of its elements is in ``expanded``, or it is the hovered group.
    An open group of several elements lays its icons out in one row from the
    group's position, since those elements' own icons would overlap.

    Returns ``(quads, hits)``: ``quads`` as arrays of centers, half sizes, atlas
    cell codes (into ``prepared["names"]``) and colors, and ``hits`` as consumed
    by ``pick`` (with each group's count, drawn as text).
    """
    half = size / 2.0
    element = prepared["element"]
    n_elements = len(prepared["element_names"])
    # Where each element's stack of icons starts.
    firsts = centers.copy()
    firsts[:, 0] -= prepared["stack"] * stack_step
    anchors = np.zeros((n_elements, 2))
    anchors[element[::-1]] = firsts[::-1]

    counts = np.bincount(element[visible], minlength=n_elements)
    shown = np.flatnonzero(counts)
    index = prepared["element_index"]
    cluster_of = np.full(n_elements, -1, dtype=np.int64)
    if mode == "NEARBY" and shown.size:
        labels = _nearby_labels(anchors[shown], size)
        # Clusters in the order their first element appears.
        _unique, first, inverse = np.unique(
            labels, return_index=True, return_inverse=True
        )
        order = np.argsort(first, kind="stable")
        rank = np.empty_like(order)
        rank[order] = np.arange(len(order))
        cluster_of[shown] = rank[inverse.ravel()]
        representative = shown[np.sort(first)]
    else:
        cluster_of[shown] = np.arange(shown.size)
        representative = shown
    n_clusters = len(representative)
    cluster_counts = np.bincount(
        cluster_of[shown], weights=counts[shown], minlength=n_clusters
    )

    open_clusters = cluster_counts <= 1
    if mode == "OFF":
        open_clusters[:] = True
    for name in expanded:
        e = index.get(name)
        if e is not None and cluster_of[e] >= 0:
            open_clusters[cluster_of[e]] = True
    hovered = -1
    if _hover["group"] is not None:
        e = index.get(_hover["group"])
        if e is not None and cluster_of[e] >= 0:
            hovered = cluster_of[e]
            open_clusters[hovered] = True

    icon_cluster = np.where(visible, cluster_of[element], -1)
    icons = visible & open_clusters[icon_cluster]

    # Open groups of several elements: one row from the group's position.
    placed = centers.copy()
    elements_in = np.bincount(cluster_of[shown], minlength=n_clusters)
    k = np.flatnonzero(icons & (elements_in[icon_cluster] > 1))
    if k.size:
        order = k[np.lexsort((prepared["stack"][k], element[k], icon_cluster[k]))]
        runs = icon_cluster[order]
        run_start = np.flatnonzero(np.r_[True, runs[1:] != runs[:-1]])
        row = np.arange(order.size) - np.repeat(
            run_start, np.diff(np.r_[run_start, order.size])
        )
        placed[order] = anchors[representative[runs]]
        placed[order, 0] += row * stack_step

    hover_rect = None
    if hovered >= 0:
        points = placed[icon_cluster == hovered]
        hover_rect = (points.min(axis=0) - half, points.max(axis=0) + half)

    collapsed = np.flatnonzero(~open_clusters)
    members = visible & ~open_clusters[icon_cluster]
    group_centers = anchors[representative[collapsed]]
    group_codes = np.empty(collapsed.size, dtype=np.int64)
    group_colors = np.empty((collapsed.size, 4), dtype=np.float32)
    if collapsed.size:
        k = np.flatnonzero(members)
        slot = np.searchsorted(collapsed, icon_cluster[k])
        # The standout color: the highest priority icon of each group.
        by_priority = np.lexsort((-prepared["priority"][k], slot))
        first = np.unique(slot[by_priority], return_index=True)[1]
        group_colors[:] = prepared["colors"][k[by_priority[first]]]
        # The most common icon type.
        n_codes = len(prepared["names"])
        tally = np.bincount(
            slot * n_codes + prepared["codes"][k], minlength=collapsed.size * n_codes
        )
        group_codes[:] = tally.reshape(collapsed.size, n_codes).argmax(axis=1)

    badge = _badge_quads(
        group_centers, size, cluster_counts[collapsed].astype(np.int64), prepared
    )
    quads = {
        "centers": np.concatenate((placed[icons], group_centers, badge["centers"])),
        "halves": np.concatenate(
            (
                np.full(int(icons.sum()) + collapsed.size, half),
                badge["halves"],
            )
        ),
        "codes": np.concatenate(
            (prepared["codes"][icons], group_codes, badge["codes"])
        ),
        "colors": np.concatenate(
            (prepared["colors"][icons], group_colors, badge["colors"])
        ),
    }
    hits = {
        "radius": size,
        "icon_centers": placed[icons],
        "icon_entries": prepared["entries"][icons],
        "group_centers": group_centers,
        "group_keys": [prepared["element_names"][e] for e in representative[collapsed]],
        "group_counts": cluster_counts[collapsed].astype(np.int64),
        "hover_rect": hover_rect,
    }
    return quads, hits


def _nearby_labels(points, size):
    """A cluster label per point, joining points whose icons would overlap.

    Points closer than an icon size join, and so do chains of them. Candidate
    pairs come from the point's own and neighbouring icon-sized grid cells, so
    no pair outside them is compared, and all of it runs as array operations.
    """
    n = len(points)
    labels = np.arange(n)
    if n < 2:
        return labels
    cells = np.floor(points / size).astype(np.int64)
    # Keys that sort by cell and can be looked up; offsets keep them positive.
    base = cells.min(axis=0) - 1
    width = int(cells[:, 1].max() - base[1]) + 2

    def cell_key(cx, cy):
        return (cx - base[0]) * width + (cy - base[1])

    keys = cell_key(cells[:, 0], cells[:, 1])
    order = np.argsort(keys, kind="stable")
    sorted_keys = keys[order]

    first, second = [], []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            wanted = cell_key(cells[:, 0] + dx, cells[:, 1] + dy)
            lo = np.searchsorted(sorted_keys, wanted, side="left")
            hi = np.searchsorted(sorted_keys, wanted, side="right")
            counts = hi - lo
            total = int(counts.sum())
            if not total:
                continue
            i = np.repeat(np.arange(n), counts)
            within = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
            j = order[np.repeat(lo, counts) + within]
            close = (i < j) & (((points[i] - points[j]) ** 2).sum(axis=1) < size * size)
            first.append(i[close])
            second.append(j[close])
    if not first:
        return labels
    i, j = np.concatenate(first), np.concatenate(second)
    if not i.size:
        return labels
    while True:
        previous = labels.copy()
        np.minimum.at(labels, i, labels[j])
        np.minimum.at(labels, j, labels[i])
        if np.array_equal(labels, previous):
            return labels


def _badge_quads(group_centers, size, counts, prepared):
    """A dark disc at each group icon's top right, for its count."""
    discs = _badge_centers(group_centers, size)
    return {
        "centers": discs,
        "halves": np.full(len(discs), size * _BADGE_RADIUS),
        "codes": np.full(len(discs), prepared["code_of"]["BADGE"], dtype=np.int64),
        "colors": np.tile(np.array(_BADGE_COLOR, dtype=np.float32), (len(discs), 1)),
    }


def _badge_centers(group_centers, size):
    return np.asarray(group_centers, dtype=np.float64).reshape(-1, 2) + (
        size * _BADGE_OFFSET
    )


# (font size, count) -> text and its offset from the badge center.
_count_texts = {}


def _draw_counts(hits):
    """Each group's count on its badge, in the interface font."""
    import blf

    counts = hits["group_counts"]
    if not len(counts):
        return
    size = hits["radius"]
    font_id = 0
    font_size = max(_COUNT_MIN_SIZE, size * _BADGE_RADIUS * _COUNT_SIZE)
    blf.size(font_id, font_size)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    position, draw = blf.position, blf.draw
    centers = _badge_centers(hits["group_centers"], size).tolist()
    for (x, y), count in zip(centers, counts.tolist()):
        key = (font_size, count)
        text = _count_texts.get(key)
        if text is None:
            label = str(min(count, 99))
            width, _height = blf.dimensions(font_id, label)
            _width, height = blf.dimensions(font_id, "0")
            text = _count_texts[key] = (label, width / 2.0, height / 2.0)
        label, dx, dy = text
        position(font_id, x - dx, y - dy, 0)
        draw(font_id, label)


def _build_batch(context, prepared, shader, uvs, mode="OFF", expanded=frozenset()):
    """The icon batch, and what was drawn for picking (see ``_arrange``)."""
    if not len(prepared["entries"]):
        return None, None
    centers, visible, size = _screen_centers(
        context, prepared["positions"], prepared["stack"]
    )
    if not visible.any():
        return None, None
    stack_step = size * context.preferences.system.ui_scale
    quads, hits = _arrange(prepared, centers, visible, size, stack_step, mode, expanded)

    corner = np.array(
        ((-1, -1), (1, -1), (1, 1), (-1, -1), (1, 1), (-1, 1)), dtype=np.float64
    )
    verts = (
        quads["centers"][:, None, :] + quads["halves"][:, None, None] * corner[None]
    ).reshape(-1, 2)
    uv_table = np.array([uvs[name] for name in prepared["names"]], dtype=np.float32)
    rects = uv_table[quads["codes"]]
    # (u0, v0), (u1, v0), (u1, v1), (u0, v0), (u1, v1), (u0, v1) per quad.
    texco = rects[:, [0, 1, 2, 1, 2, 3, 0, 1, 2, 3, 0, 3]].reshape(-1, 2)
    colors = np.repeat(quads["colors"], 6, axis=0)
    batch = batch_for_shader(
        shader,
        "TRIS",
        {"pos": verts.astype(np.float32), "texCoord": texco, "color": colors},
    )
    return batch, hits
