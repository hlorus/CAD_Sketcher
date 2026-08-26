"""Migrate legacy entity-based sketches to the native-curve model.

Old files store geometry as SlvsPoint2D/Line2D/Arc/Circle entities under
``scene.sketcher.entities``, grouped by SlvsSketch entities on SlvsWorkplane
entities. The native-curve model stores each sketch as a Curves object (parented
to a workplane Empty) with geometry in curve data.

This module rebuilds the new representation from the old entities using the same
``PointRef/LineRef/ArcRef/CircleRef.create`` constructors the operators use.
Constraints are NOT migrated here (that's a separate phase); only geometry.

The old entity data is left intact (it's the migration source and is kept for
loading even older files).
"""

import logging

import bpy

logger = logging.getLogger(__name__)


def _iter_legacy_sketches(context):
    """Legacy SlvsSketch entities still needing migration.

    A sketch is legacy if its ``target_object`` is not (yet) a native-curve
    sketch — in old files it points at the generated mesh output instead.
    """
    from ..model.sketch import SlvsSketch
    from ..model.sketch_ref import is_sketch_object

    for e in context.scene.sketcher.entities.all:
        if not isinstance(e, SlvsSketch) or not e.wp:
            continue
        if is_sketch_object(e.target_object):
            continue
        yield e


def scene_needs_migration(context):
    return next(_iter_legacy_sketches(context), None) is not None


def _create_workplane_empty(context, wp, name):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.5
    empty.lock_location = (True, True, True)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)
    context.scene.collection.objects.link(empty)
    empty.matrix_world = wp.matrix_basis
    return empty


def _create_sketch_object(context, empty, name):
    from ..model.sketch_ref import Sketch, stamp_sketch_props
    from ..utilities.curve_data import _ensure_convert_modifier

    curve = bpy.data.hair_curves.new(name)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    stamp_sketch_props(obj)
    _ensure_convert_modifier(obj)
    obj.parent = empty
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)
    return Sketch(obj)


def _migrate_geometry(context, old_sketch, sketch, entity_map):
    """Rebuild an old sketch's 2D entities as curves. Returns (n_points, n_segs).

    ``entity_map`` is populated with ``old slvs_index -> (sketch, curve_id)`` for
    every migrated entity, so constraints can be remapped afterwards.
    """
    from ..model.arc import SlvsArc
    from ..model.circle import SlvsCircle
    from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef
    from ..model.line_2d import SlvsLine2D
    from ..model.point_2d import SlvsPoint2D

    ents = list(old_sketch.sketch_entities(context))
    point_map = {}  # old slvs_index -> new PointRef
    wp_inv = old_sketch.wp.matrix_basis.inverted()

    # Points first, so segments can reference them.
    for e in ents:
        if isinstance(e, SlvsPoint2D):
            pr = PointRef.create(
                sketch,
                (e.co[0], e.co[1]),
                construction=getattr(e, "construction", False),
                fixed=getattr(e, "fixed", False),
            )
            point_map[e.slvs_index] = pr
            entity_map[e.slvs_index] = (sketch, pr.curve_id)

    def pt(entity):
        """Resolve a point ref, creating a local copy for cross-sketch points.

        A segment may reference a point owned by another sketch; the per-sketch
        curve model can't share it, so copy it into this sketch at the same
        position (projected into this sketch's workplane).
        """
        if entity is None:
            return None
        pr = point_map.get(entity.slvs_index)
        if pr is not None:
            return pr
        if not isinstance(entity, SlvsPoint2D):
            return None
        local = wp_inv @ entity.location
        pr = PointRef.create(
            sketch,
            (local.x, local.y),
            construction=getattr(entity, "construction", False),
        )
        point_map[entity.slvs_index] = pr
        return pr

    n_seg = 0
    for e in ents:
        con = getattr(e, "construction", False)
        ref = None
        if isinstance(e, SlvsLine2D):
            p1, p2 = pt(e.p1), pt(e.p2)
            if p1 and p2:
                ref = LineRef.create(sketch, p1, p2, construction=con)
        elif isinstance(e, SlvsArc):
            ct, s, en = pt(e.ct), pt(e.start), pt(e.end)
            if ct and s and en:
                ref = ArcRef.create(sketch, ct, s, en, construction=con)
        elif isinstance(e, SlvsCircle):
            ct = pt(e.ct)
            if ct:
                ref = CircleRef.create(sketch, ct, e.radius, construction=con)
        if ref is not None:
            entity_map[e.slvs_index] = (sketch, ref.curve_id)
            n_seg += 1

    return len(point_map), n_seg


# ---------------------------------------------------------------------------
# Modifier translation
#
# In old files a sketch's ``target_object`` was the generated MESH output, and
# users stacked ordinary mesh modifiers on it to build the finished part. New
# sketches are Curves objects, which mesh modifiers cannot be added to, so the
# old stack would be orphaned. Rebuild the translatable modifiers as the addon's
# Geometry Nodes node tools (or a native GN node) on the new Curves sketch, in
# order. Anything without a GN equivalent (e.g. Bevel -- Blender has no bevel
# node) is skipped and recorded so the user knows exactly what was dropped.
# ---------------------------------------------------------------------------


def _load_node_group(name):
    from ..assets_manager import load_asset

    if load_asset("node_groups", name):
        return bpy.data.node_groups.get(name)
    return None


def _add_gn_modifier(obj, name, build):
    """Add a GN modifier wrapping a small built-in node construction.

    ``build(nodes, links, geometry_socket)`` wires nodes onto the input geometry
    and returns the output geometry socket. Params are baked into a fresh group
    per modifier (they are small), so no shared-group value conflicts arise.
    """
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(
        "Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    ng.interface.new_socket(
        "Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    out = build(nodes, links, gi.outputs["Geometry"])
    links.new(out, go.inputs["Geometry"])
    modifier = obj.modifiers.new(name, "NODES")
    modifier.node_group = ng
    return modifier


def _translate_weld(mod, old_mesh, obj):
    """Weld -> Merge by Distance (collapse vertices within a threshold)."""
    distance = float(getattr(mod, "merge_threshold", 0.001))

    def build(nodes, links, geo):
        merge = nodes.new("GeometryNodeMergeByDistance")
        links.new(geo, merge.inputs["Geometry"])
        merge.inputs["Distance"].default_value = distance
        return merge.outputs["Geometry"]

    _add_gn_modifier(obj, "CAD_Sketcher Weld", build)
    return True


def _translate_subsurf(mod, old_mesh, obj):
    """Subdivision Surface -> the Subdivision Surface node (viewport levels)."""
    levels = int(getattr(mod, "levels", 1))

    def build(nodes, links, geo):
        sub = nodes.new("GeometryNodeSubdivisionSurface")
        links.new(geo, sub.inputs["Mesh"])
        sub.inputs["Level"].default_value = levels
        return sub.outputs["Mesh"]

    _add_gn_modifier(obj, "CAD_Sketcher Subdivision", build)
    return True


def _translate_triangulate(mod, old_mesh, obj):
    """Triangulate -> the Triangulate node (default methods)."""

    def build(nodes, links, geo):
        tri = nodes.new("GeometryNodeTriangulate")
        links.new(geo, tri.inputs["Mesh"])
        return tri.outputs["Mesh"]

    _add_gn_modifier(obj, "CAD_Sketcher Triangulate", build)
    return True


def _translate_mirror(mod, old_mesh, obj):
    """Mirror -> a per-axis GN construction (scale -1, flip faces, join, merge).

    Only the axis mirror (across the object's local origin) is handled; a mirror
    across a separate ``mirror_object`` has no clean equivalent, so it is skipped.
    """
    if getattr(mod, "mirror_object", None) is not None:
        return False
    axes = [i for i in range(3) if mod.use_axis[i]]
    if not axes:
        return False
    do_merge = bool(getattr(mod, "use_mirror_merge", True))
    threshold = float(getattr(mod, "merge_threshold", 0.001))

    def build(nodes, links, geo):
        current = geo
        for axis in axes:
            scale = [1.0, 1.0, 1.0]
            scale[axis] = -1.0
            xf = nodes.new("GeometryNodeTransform")
            links.new(current, xf.inputs["Geometry"])
            xf.inputs["Scale"].default_value = tuple(scale)
            flip = nodes.new("GeometryNodeFlipFaces")
            links.new(xf.outputs["Geometry"], flip.inputs["Mesh"])
            join = nodes.new("GeometryNodeJoinGeometry")
            links.new(current, join.inputs["Geometry"])
            links.new(flip.outputs["Mesh"], join.inputs["Geometry"])
            current = join.outputs["Geometry"]
        if do_merge:
            merge = nodes.new("GeometryNodeMergeByDistance")
            links.new(current, merge.inputs["Geometry"])
            merge.inputs["Distance"].default_value = threshold
            current = merge.outputs["Geometry"]
        return current

    _add_gn_modifier(obj, "CAD_Sketcher Mirror", build)
    return True


def _translate_solidify(mod, old_mesh, obj):
    """Solidify gives a profile thickness -- the same as the Extrude tool."""
    from ..operators.modifiers import set_modifier_input

    ng = _load_node_group("CAD Sketcher Extrude")
    if ng is None:
        return False
    from .extrude_nodes import ensure_extrude_edge_walls

    ensure_extrude_edge_walls(ng)
    m = obj.modifiers.new("CAD_Sketcher Extrude", "NODES")
    m.node_group = ng
    set_modifier_input(m, "Input_2", float(mod.thickness))  # Size
    return True


def _translate_boolean(mod, old_mesh, obj, cutter_map=None):
    """Boolean -> the CAD Sketcher Boolean node group, reading the same cutter.

    ``cutter_map`` maps a legacy generated mesh to the new Curves sketch that
    replaced it. If the cutter was itself a migrated sketch's output, point the
    new boolean at that sketch instead of the orphaned (soon removed) old mesh.
    """
    cutter = mod.object
    if cutter is None:
        return False
    if cutter_map is not None:
        cutter = cutter_map.get(cutter, cutter)
    from ..operators.modifiers import (
        boolean_input_ids,
        set_boolean_operation,
        set_modifier_input,
    )
    from .boolean_nodes import build_boolean_node_group

    ng = build_boolean_node_group()
    m = obj.modifiers.new(f"CAD_Sketcher Boolean {cutter.name}", "NODES")
    m.node_group = ng
    ids = boolean_input_ids(ng)
    set_modifier_input(m, ids["Cutter"], cutter)
    op = {"DIFFERENCE": "Difference", "UNION": "Union", "INTERSECT": "Intersect"}[
        mod.operation
    ]
    set_boolean_operation(m, ids["Operation"], op)
    return True


def _translate_array(mod, old_mesh, obj):
    """Array -> the Linear Array node group. The old offset is a mix of a
    relative (fraction of the object's bounds) and a constant part; combine both
    into one world-space offset, then split into direction + spacing."""
    from mathutils import Vector

    from ..operators.modifiers import set_modifier_input

    offset = Vector((0.0, 0.0, 0.0))
    if mod.use_constant_offset:
        offset += Vector(mod.constant_offset_displace)
    if mod.use_relative_offset:
        dims = old_mesh.dimensions
        rel = mod.relative_offset_displace
        offset += Vector((rel[0] * dims.x, rel[1] * dims.y, rel[2] * dims.z))
    if offset.length < 1e-9:
        return False  # no derivable direction

    ng = _load_node_group("CAD Sketcher Linear Array")
    if ng is None:
        return False
    m = obj.modifiers.new("CAD_Sketcher Linear Array", "NODES")
    m.node_group = ng
    set_modifier_input(m, "Input_21", tuple(offset.normalized()))  # Direction
    set_modifier_input(m, "Input_22", int(mod.count))  # Count
    set_modifier_input(m, "Input_23", offset.length)  # Spacing
    return True


def _translate_screw(mod, old_mesh, obj):
    """Screw -> the Revolve tool. Best-effort: map the axis, angle, and step
    resolution; ignore the params Revolve has no concept of (helical screw
    offset, iterations, axis-object override)."""
    from ..operators.modifiers import set_modifier_input
    from .revolve_nodes import _input_ids, build_revolve_node_group

    axis_dir = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}.get(
        getattr(mod, "axis", "Z")
    )
    if axis_dir is None:
        return False

    ng = build_revolve_node_group()
    angle = float(getattr(mod, "angle", 6.283185307179586))
    steps = max(1, int(getattr(mod, "steps", 16)))

    m = obj.modifiers.new("CAD_Sketcher Revolve", "NODES")
    m.node_group = ng
    ids = _input_ids(ng)
    set_modifier_input(m, ids["Axis Origin"], (0.0, 0.0, 0.0))  # local origin
    set_modifier_input(m, ids["Axis Direction"], axis_dir)
    set_modifier_input(m, ids["Angle"], angle)
    set_modifier_input(m, ids["Angular Resolution"], abs(angle) / steps)
    return True


_MODIFIER_TRANSLATORS = {
    "SOLIDIFY": _translate_solidify,
    "BOOLEAN": _translate_boolean,
    "ARRAY": _translate_array,
    "SCREW": _translate_screw,
    "WELD": _translate_weld,
    "SUBSURF": _translate_subsurf,
    "TRIANGULATE": _translate_triangulate,
    "MIRROR": _translate_mirror,
}


def _migrate_modifiers(old_mesh, sketch, summary, cutter_map=None):
    """Rebuild ``old_mesh``'s modifier stack as GN siblings on ``sketch``.

    Isolated per modifier: a failed or unsupported one is skipped and recorded,
    never aborting the rest of the migration. ``cutter_map`` (old mesh -> new
    sketch object) lets boolean cutters be remapped onto migrated sketches.
    """
    obj = sketch.target_object
    if obj is None:
        return
    for mod in list(old_mesh.modifiers):
        try:
            translator = _MODIFIER_TRANSLATORS.get(mod.type)
            if translator is None:
                summary["modifiers_skipped"].append(f"{old_mesh.name}: {mod.type}")
                continue
            if mod.type == "BOOLEAN":
                ok = translator(mod, old_mesh, obj, cutter_map)
            else:
                ok = translator(mod, old_mesh, obj)
            if ok:
                summary["modifiers"] += 1
            else:
                summary["modifiers_skipped"].append(f"{old_mesh.name}: {mod.type}")
        except Exception as e:
            logger.exception("Failed to migrate modifier %s", mod.name)
            summary["modifiers_skipped"].append(f"{old_mesh.name}: {mod.type} ({e!r})")


def _remove_legacy_meshes(old_meshes, summary):
    """Delete the orphaned legacy generated meshes after their stacks migrated.

    The new Curves sketches (with their translated GN modifiers) are now the
    extension's output, so the old meshes would only duplicate the geometry.
    """
    for old_mesh in list(old_meshes):
        try:
            data = old_mesh.data
            bpy.data.objects.remove(old_mesh, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
            summary["meshes_removed"] += 1
        except Exception as e:
            logger.exception("Failed to remove legacy mesh %s", old_mesh)
            summary["errors"].append(f"remove mesh: {e!r}")


def migrate_scene(context):
    """Migrate all legacy sketches (geometry + constraints). Returns a summary."""
    summary = {
        "sketches": 0,
        "points": 0,
        "segments": 0,
        "constraints": 0,
        "constraints_skipped": 0,
        "errors": [],
        "modifiers": 0,
        "modifiers_skipped": [],
        "meshes_removed": 0,
    }

    # One Empty per distinct legacy workplane (sketches sharing a plane share it).
    wp_empties = {}
    # old entity slvs_index -> (new Sketch, curve_id) for constraint remapping.
    entity_map = {}
    # Legacy generated mesh -> new sketch (deferred), and old mesh -> new sketch
    # object (for remapping boolean cutters that reference another sketch).
    pending_modifiers = []
    mesh_to_sketch_obj = {}

    for old_sketch in list(_iter_legacy_sketches(context)):
        try:
            wp = old_sketch.wp
            empty = wp_empties.get(wp.slvs_index)
            if empty is None:
                empty = _create_workplane_empty(
                    context, wp, f"WP_{getattr(wp, 'name', 'Workplane')}"
                )
                wp_empties[wp.slvs_index] = empty

            # The legacy target_object is the old generated mesh (with the user's
            # modifier stack); capture it before re-pointing to the new sketch.
            old_mesh = old_sketch.target_object

            sketch = _create_sketch_object(context, empty, old_sketch.name or "Sketch")
            # Link old->new so re-runs skip it and future phases can find it.
            old_sketch.target_object = sketch.target_object

            n_pts, n_seg = _migrate_geometry(context, old_sketch, sketch, entity_map)
            if old_mesh is not None and getattr(old_mesh, "type", None) == "MESH":
                mesh_to_sketch_obj[old_mesh] = sketch.target_object
                pending_modifiers.append((old_mesh, sketch))
            summary["sketches"] += 1
            summary["points"] += n_pts
            summary["segments"] += n_seg
        except Exception as e:
            logger.exception("Failed to migrate sketch %s", old_sketch)
            summary["errors"].append(f"{old_sketch.name}: {e!r}")

    # Translate modifier stacks only after every old->new link is known, so a
    # boolean cutting with another sketch's output can be remapped correctly.
    for old_mesh, sketch in pending_modifiers:
        _migrate_modifiers(old_mesh, sketch, summary, cutter_map=mesh_to_sketch_obj)

    _remove_legacy_meshes(mesh_to_sketch_obj.keys(), summary)

    _migrate_constraints(context, entity_map, summary)
    return summary


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

# Simple (non-dimensional) two-reference constraints: type -> add method name.
_SIMPLE_CONSTRAINTS = {
    "COINCIDENT": "add_coincident",
    "EQUAL": "add_equal",
    "VERTICAL": "add_vertical",
    "HORIZONTAL": "add_horizontal",
    "PARALLEL": "add_parallel",
    "PERPENDICULAR": "add_perpendicular",
    "TANGENT": "add_tangent",
    "MIDPOINT": "add_midpoint",
}


def _dim_settings(old):
    """Value/flag settings carried onto a migrated dimensional constraint.

    The legacy numeric value is a raw ID-property (``old["value"]``); the RNA
    ``value`` getter shadows it (it reads the new uid-keyed scene storage), so
    read the ID-property directly.
    """
    s = {}
    val = old.get("value")
    if val is not None:
        s["value"] = float(val)
    for key in ("setting", "is_reference"):
        if hasattr(old, key):
            s[key] = getattr(old, key)
    return s


def _add_migrated_constraint(cons, ctype, cids, old):
    """Create the new constraint on ``cons`` (a sketch's SlvsConstraints)."""
    c1, c2, c3 = cids
    if ctype in _SIMPLE_CONSTRAINTS:
        getattr(cons, _SIMPLE_CONSTRAINTS[ctype])(c1, c2)
    elif ctype == "DISTANCE":
        cons.add_distance(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "ANGLE":
        cons.add_angle(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "DIAMETER":
        cons.add_diameter(curve_id_1=c1, **_dim_settings(old))
    elif ctype == "RATIO":
        cons.add_ratio(curve_id_1=c1, curve_id_2=c2, **_dim_settings(old))
    elif ctype == "SYMMETRY":
        cons.add_symmetry(c1, c2, c3)
    else:
        return False
    return True


def _migrate_constraints(context, entity_map, summary):
    """Rebuild legacy constraints on the migrated sketches via curve_id refs."""
    for old in list(context.scene.sketcher.constraints.all):
        try:
            ctype = getattr(old, "type", None)
            refs = [getattr(old, n, None) for n in ("entity1", "entity2", "entity3")]
            mapped = [
                entity_map.get(r.slvs_index) if r is not None else None for r in refs
            ]
            present = [m for m in mapped if m]
            if not present:
                summary["constraints_skipped"] += 1
                continue

            # Place the constraint on the sketch of its first mapped reference.
            sketch = present[0][0]
            cids = [m[1] if m else "" for m in mapped]
            if _add_migrated_constraint(sketch.constraints, ctype, cids, old):
                summary["constraints"] += 1
            else:
                summary["constraints_skipped"] += 1
        except Exception as e:
            logger.exception("Failed to migrate constraint %s", old)
            summary["errors"].append(f"constraint {ctype}: {e!r}")
