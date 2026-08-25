"""Reusable, state-aware hover gizmo.

Publishes the element under the cursor to ``global_data.hover_element`` so
object/mesh-picking tools can highlight what the current stateful-operator state
will pick. Mirrors the preselection gizmo: ``test_select`` runs on every
mouse-move (including mid-modal, since pointer states pass mouse-moves through)
and never claims the click (returns -1). The highlight is rendered by the draw
handler (see draw_handler.draw_hover_element).

What it detects is driven by ``global_data.hover_types`` — the accepted types of
the operator's current state. Before the operator runs the state types are not
published yet, so the idle preview falls back to the active tool's own pick
types (see ``_IDLE_HOVER_TYPES``): the object-base tools keep their whole-object
highlight, while the projection tool previews the exact vertex/edge/face and
never the whole object. Objects are found via a bounding-box screen test (a
raycast can't hit a surfaceless sketch); mesh vertices/edges/faces via the
raycast-based ``get_mesh_element``.
"""

from bpy.types import Gizmo, GizmoGroup, MeshEdge, MeshPolygon, MeshVertex, Object
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from .. import global_data
from ..declarations import GizmoGroups, Gizmos, WorkSpaceTools
from ..stateful_operator.constants import mesh_element_types
from ..stateful_operator.utilities.geometry import get_mesh_element
from .utilities import context_mode_check

# Idle pick preview per ObjectHover tool: what the tool's operator will pick
# once it runs, published before it starts so the hover already tracks it. The
# node tools pick a whole base object; the projection tool picks a mesh element,
# so it must never fall back to the whole-object highlight.
_IDLE_HOVER_TYPES = {
    WorkSpaceTools.Extrude: (Object,),
    WorkSpaceTools.ArrayLinear: (Object,),
    WorkSpaceTools.Revolve: (Object,),
    WorkSpaceTools.ProjectGeometry: mesh_element_types,
}


def _idle_hover_types(context):
    """Pick types to preview while a hover tool is active but not yet running."""
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool is None:
        return None
    return _IDLE_HOVER_TYPES.get(tool.idname)


def object_under_cursor(context, coords):
    """Nearest visible object whose screen-space bounding box contains coords."""
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return None

    view_origin = rv3d.view_matrix.inverted().translation
    best = None
    best_depth = None
    for ob in context.visible_objects:
        mw = ob.matrix_world
        xs, ys = [], []
        center = Vector()
        for corner in ob.bound_box:
            world = mw @ Vector(corner)
            center += world
            p = location_3d_to_region_2d(region, rv3d, world)
            if p is not None:
                xs.append(p.x)
                ys.append(p.y)
        if not xs:
            continue
        if min(xs) <= coords.x <= max(xs) and min(ys) <= coords.y <= max(ys):
            depth = ((center / 8.0) - view_origin).length
            if best_depth is None or depth < best_depth:
                best = ob
                best_depth = depth
    return best


def detect_hover(context, coords, types):
    """Return the hover element under the cursor for the accepted ``types``.

    Precise mesh elements win over the object; returns one of
    ``("OBJECT", name, None)``, ``("VERTEX"|"EDGE"|"FACE", name, index)``, or
    ``None``. Falsy ``types`` (None or empty) means nothing to pick, so no hover
    is produced; the caller resolves the idle preview types before this point.
    """
    if not types:
        return None

    want_vertex = MeshVertex in types
    want_edge = MeshEdge in types
    want_face = MeshPolygon in types

    if want_vertex or want_edge or want_face:
        # CURVES objects (sketches / native curves) hover as whole elements --
        # points, lines, arcs, circles -- via the screen-space reference pick,
        # taking priority over a raycast hit on a sketch's converted fill mesh.
        from ..drawing.reference_pick import pick_reference_element
        from ..model.sketch_ref import get_active_sketch

        active = get_active_sketch(context)
        ref = pick_reference_element(
            context, coords, exclude=active.target_object if active else None
        )
        if ref is not None:
            ob, key = ref
            return ("CURVE_ELEM", ob.name, key)

        ob, elem_type, index = get_mesh_element(
            context, coords, vertex=want_vertex, edge=want_edge, face=want_face
        )
        if ob is not None and elem_type in ("VERTEX", "EDGE", "FACE"):
            return (elem_type, ob.name, index)

        # Legacy Curve objects (bezier/nurbs) aren't handled by reference_pick
        # yet; keep the raw segment-hover fallback for them.
        if want_edge:
            from ..utilities.view import curve_segment_under_cursor

            radius = 12.0 * context.preferences.system.ui_scale
            hit = curve_segment_under_cursor(context, coords, radius)
            if hit is not None:
                return ("EDGE", hit[0].name, hit[1])

    if Object in types:
        ob = object_under_cursor(context, coords)
        if ob is not None:
            return ("OBJECT", ob.name, None)

    return None


class VIEW3D_GGT_slvs_object_hover(GizmoGroup):
    bl_idname = GizmoGroups.ObjectHover
    bl_label = "Object Hover Gizmo Group"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    @classmethod
    def poll(cls, context):
        return context_mode_check(context, cls.bl_idname)

    def setup(self, context):
        self.gizmo = self.gizmos.new(VIEW3D_GT_slvs_object_hover.bl_idname)


class VIEW3D_GT_slvs_object_hover(Gizmo):
    bl_idname = Gizmos.ObjectHover

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        # While the operator runs, its current state publishes the pick types;
        # before that, preview what the active tool itself will pick.
        types = global_data.hover_types
        if types is None:
            types = _idle_hover_types(context)
        element = detect_hover(context, Vector(location), types)
        if element != global_data.hover_element:
            global_data.hover_element = element
            context.area.tag_redraw()
        # Never claim the click: fall through to the tool keymap / operator.
        return -1
