import logging

from bpy.utils import register_classes_factory
from bpy.props import StringProperty
from bpy.types import Operator, Context

from .. import global_data
from ..model.sketch_ref import get_active_sketch
from ..utilities.view import refresh
from ..utilities.curve_data import remove_native_curve_by_id
from ..declarations import Operators
from ..curve_solver import solve_system

logger = logging.getLogger(__name__)


def _get_dependent_curve_ids(sketch, curve_id):
    """Find curve_ids that reference this curve_id via relationship attributes."""
    from ..utilities.curve_data import get_uuid, has_uuid_field

    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return []

    cd = sketch.target_object.data
    n = len(cd.curves)
    if not has_uuid_field(cd, "curve_id"):
        return []

    deps = []
    for i in range(n):
        cid = get_uuid(cd, "curve_id", i)
        if cid == curve_id:
            continue
        if get_uuid(cd, "start_point_id", i) == curve_id:
            deps.append(cid)
        elif get_uuid(cd, "end_point_id", i) == curve_id:
            deps.append(cid)
        elif get_uuid(cd, "center_point_id", i) == curve_id:
            deps.append(cid)
    return deps


def _get_constraint_indices_for_curve_id(curve_id, context):
    """Find constraints that reference a curve_id."""
    from ..model.sketch_ref import get_active_constraints
    constraints = get_active_constraints(context)
    if not constraints:
        return []
    ret_list = []

    for data_coll in constraints.get_lists():
        indices = []
        for i, c in enumerate(data_coll):
            if getattr(c, "curve_id_1", "") == curve_id:
                indices.append(i)
            elif getattr(c, "curve_id_2", "") == curve_id:
                indices.append(i)
            elif getattr(c, "curve_id_3", "") == curve_id:
                indices.append(i)
        if indices:
            ret_list.append((data_coll, indices))
    return ret_list


class View3D_OT_slvs_delete_entity(Operator):
    """Delete selected sketch geometry"""

    bl_idname = Operators.DeleteEntity
    bl_label = "Delete Entity"
    bl_options = {"UNDO"}

    index: StringProperty(default="")

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        to_delete = []
        if self.index:
            to_delete.append(self.index)
        else:
            to_delete.extend(list(global_data.selected))

        if not to_delete:
            return {"CANCELLED"}

        for cid in to_delete:
            self._delete_curve(context, sketch, cid)

        global_data.selected.clear()
        global_data.hover = ""

        solve_system(context, sketch=sketch)
        refresh(context)
        return {"FINISHED"}

    def _delete_curve(self, context, sketch, curve_id):
        deps = _get_dependent_curve_ids(sketch, curve_id)
        if deps:
            for dep_cid in deps:
                self._delete_curve(context, sketch, dep_cid)

        for data_coll, indices in _get_constraint_indices_for_curve_id(curve_id, context):
            for i in reversed(indices):
                data_coll.remove(i)

        remove_native_curve_by_id(sketch, curve_id)


register, unregister = register_classes_factory((View3D_OT_slvs_delete_entity,))
