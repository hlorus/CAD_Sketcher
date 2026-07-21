import logging

import bpy
from bpy.types import Context, Operator

from .. import global_data
from ..declarations import BLENDER_SELECT_TOOL, GizmoGroups, WorkSpaceTools
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.preferences import get_prefs
from ..model.sketch_ref import get_active_sketch

logger = logging.getLogger(__name__)


def select_invert(context: Context):
    sketch = get_active_sketch(context)
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return

    curve_data = sketch.target_object.data
    n = len(curve_data.curves)
    cid_attr = curve_data.attributes.get("curve_id")
    if not cid_attr:
        return

    for i in range(n):
        cid = cid_attr.data[i].value
        if not cid:
            continue
        if cid in global_data.selected:
            global_data.selected.remove(cid)
        else:
            global_data.selected.append(cid)


def select_extend(context: Context):
    sketch = get_active_sketch(context)
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return False

    cd = sketch.target_object.data
    n = len(cd.curves)
    cid_attr = cd.attributes.get("curve_id")
    type_attr = cd.attributes.get("sketch_type")
    sp_attr = cd.attributes.get("start_point_id")
    ep_attr = cd.attributes.get("end_point_id")
    cp_attr = cd.attributes.get("center_point_id")
    if not cid_attr or not type_attr:
        return False

    from ..model.constants import SketchCurveType
    selected = set(global_data.selected)
    to_add = set()

    for i in range(n):
        cid = cid_attr.data[i].value
        if not cid:
            continue
        ctype = type_attr.data[i].value
        sp = sp_attr.data[i].value if sp_attr else 0
        ep = ep_attr.data[i].value if ep_attr else 0
        cp = cp_attr.data[i].value if cp_attr else 0
        rel_ids = {r for r in (sp, ep, cp) if r}

        if ctype == SketchCurveType.POINT:
            # Point selected → select segments referencing it
            if cid in selected:
                for j in range(n):
                    j_cid = cid_attr.data[j].value
                    j_sp = sp_attr.data[j].value if sp_attr else 0
                    j_ep = ep_attr.data[j].value if ep_attr else 0
                    j_cp = cp_attr.data[j].value if cp_attr else 0
                    if cid in (j_sp, j_ep, j_cp):
                        to_add.add(j_cid)
        else:
            # Segment selected → select its points
            if cid in selected:
                to_add.update(rel_ids)
            # Segment has a selected point → select the segment
            elif rel_ids & selected:
                to_add.add(cid)

    # Follow coincident constraints
    sketch = get_active_sketch(context)
    coincident = sketch.constraints.coincident if sketch else []
    for c in coincident:
        c1, c2 = getattr(c, 'curve_id_1', ""), getattr(c, 'curve_id_2', "")
        if c1 in selected and c2:
            to_add.add(c2)
        if c2 in selected and c1:
            to_add.add(c1)

    new = to_add - selected
    for cid in new:
        global_data.selected.append(cid)
    return len(new) > 0


# NOTE: The draw handler has to be registered before this has any effect, currently it's possible that
# entities are first created with an entity that was hovered in the previous state
# Not sure if it's possible to force draw handlers...
# Also note that a running modal operator might prevent redraws, avoid returning running_modal
def ignore_hover(ref_or_id):
    """Add a curve_id to the ignore list. Accepts CurveRef, curve_id int, or entity."""
    from ..model.curve_ref import CurveRef
    ignore_list = global_data.ignore_list
    if isinstance(ref_or_id, CurveRef):
        ignore_list.append(ref_or_id.curve_id)
    elif isinstance(ref_or_id, (int, str)):
        ignore_list.append(ref_or_id)
    else:
        # Legacy entity — use slvs_index
        ignore_list.append(ref_or_id.slvs_index)


def get_hovered(context: Context, *types):
    """Get the hovered CurveRef if it matches one of the accepted types.

    Types can be CurveRef subclasses (PointRef, LineRef, etc.) or legacy
    entity classes (SlvsPoint2D, SlvsLine2D, etc.).
    """
    from ..model.curve_ref import curve_ref, PointRef, LineRef, ArcRef, CircleRef

    hover_id = global_data.hover
    if not hover_id:
        return None

    sketch = get_active_sketch(context)
    if not sketch:
        return None

    ref = curve_ref(sketch, hover_id)
    if not ref.valid:
        return None

    # Map legacy entity types to CurveRef types for matching
    from ..model.types import SlvsPoint2D, SlvsLine2D, SlvsArc, SlvsCircle
    _type_map = {
        SlvsPoint2D: PointRef,
        SlvsLine2D: LineRef,
        SlvsArc: ArcRef,
        SlvsCircle: CircleRef,
    }

    for t in types:
        # Direct CurveRef subclass check
        if isinstance(ref, t) if isinstance(t, type) and issubclass(t, (PointRef, LineRef, ArcRef, CircleRef)) else False:
            return ref
        # Legacy entity type → mapped CurveRef type
        mapped = _type_map.get(t)
        if mapped and isinstance(ref, mapped):
            return ref

    return None


SMOOTHVIEW_FACTOR = 0


def align_view(rv3d, mat_start, mat_end):

    global SMOOTHVIEW_FACTOR
    SMOOTHVIEW_FACTOR = 0
    time_step = 0.01
    increment = 0.01

    def move_view():
        global SMOOTHVIEW_FACTOR
        SMOOTHVIEW_FACTOR += increment
        mat = mat_start.lerp(mat_end, SMOOTHVIEW_FACTOR)
        rv3d.view_matrix = mat

        if SMOOTHVIEW_FACTOR < 1:
            return time_step

    bpy.app.timers.register(move_view)

    # rv3d.view_distance = 6


def switch_sketch_mode(self, context: Context, to_sketch_mode: bool):
    from ..workspacetools.manager import enter_sketch_mode, leave_sketch_mode

    if to_sketch_mode:
        enter_sketch_mode()
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        if tool.widget != GizmoGroups.Preselection:
            bpy.ops.wm.tool_set_by_id(name=WorkSpaceTools.Select)
        return True

    bpy.ops.wm.tool_set_by_id(name=BLENDER_SELECT_TOOL)
    leave_sketch_mode()
    return True


def activate_sketch(context: Context, sketch_obj, operator: Operator):
    """Activate a sketch (Curves object) or deactivate (pass None)."""
    from ..model.sketch_ref import Sketch, set_active_sketch, get_active_sketch

    space_data = context.space_data
    props = context.scene.sketcher

    current = get_active_sketch(context)
    if sketch_obj is not None and current and current.target_object == sketch_obj:
        return {"CANCELLED"}

    sketch_mode = sketch_obj is not None
    switch_sketch_mode(self=operator, context=context, to_sketch_mode=sketch_mode)

    last = current
    set_active_sketch(context, sketch_obj)

    # Align view (after setting active sketch)
    if get_prefs().use_align_view:
        bpy.ops.view3d.slvs_align_view(use_active=True)

    # Hide objects
    fade_objects = get_prefs().auto_hide_objects
    if fade_objects:
        space_data.shading.show_xray = sketch_mode

    logger.debug("Activate: {}".format(sketch_obj))
    context.area.tag_redraw()

    if context.mode != "OBJECT":
        return {"FINISHED"}

    if last:
        refresh_curve_geometry(last)

    if sketch_obj is None and last:
        select_target_ob(context, last)

    return {"FINISHED"}


def select_target_ob(context, sketch):
    target_ob = sketch.target_object

    bpy.ops.object.select_all(action="DESELECT")
    if not target_ob:
        return

    if target_ob.name in context.view_layer.objects:
        target_ob.select_set(True)
        context.view_layer.objects.active = target_ob
