import logging

from bpy.props import StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..curve_solver import solve_system
from ..declarations import Operators
from ..drawing import selection
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import remove_native_curve_by_id
from ..utilities.highlighting import HighlightElement
from ..utilities.view import refresh

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


def _is_origin_curve(sketch, curve_id):
    """True if curve_id is the sketch's protected origin point."""
    from ..utilities.curve_data import get_curve_data

    cd, idx, _ = get_curve_data(sketch, curve_id)
    if cd is None:
        return False
    attr = cd.attributes.get("is_origin")
    return bool(attr.data[idx].value) if attr else False


def _get_constraint_indices_for_curve_id(sketch, curve_id):
    """Find constraints of ``sketch`` that reference a curve_id."""
    constraints = sketch.constraints if sketch else None
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


def delete_curve(sketch, curve_id: str) -> None:
    """Delete one curve from ``sketch``, with what depends on it.

    Curves built on the curve go first (a line cannot outlive its endpoint), then
    the constraints that reference any of them, so nothing is left pointing at
    geometry that is gone. The sketch origin is permanent and ignored.
    """
    if _is_origin_curve(sketch, curve_id):
        return

    for dep_cid in _get_dependent_curve_ids(sketch, curve_id):
        delete_curve(sketch, dep_cid)

    for data_coll, indices in _get_constraint_indices_for_curve_id(sketch, curve_id):
        for i in reversed(indices):
            data_coll.remove(i)

    remove_native_curve_by_id(sketch, curve_id)


class View3D_OT_slvs_delete_entity(Operator, HighlightElement):
    """Delete selected sketch geometry"""

    bl_idname = Operators.DeleteEntity
    bl_label = "Delete Entity"
    bl_options = {"UNDO"}

    index: StringProperty(default="")

    @classmethod
    def description(cls, context, properties):
        cls.handle_highlight_hover(context, properties)
        if properties.index:
            sketch = get_active_sketch(context)
            if sketch and _is_origin_curve(sketch, properties.index):
                return "Cannot delete the sketch origin"
        return cls.__doc__

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        to_delete = []
        if self.index:
            to_delete.append(self.index)
        else:
            to_delete.extend(list(selection.selected))

        if not to_delete:
            return {"CANCELLED"}

        for cid in to_delete:
            delete_curve(sketch, cid)

        selection.selected.clear()
        selection.hover = ""

        solve_system(context, sketch=sketch)
        refresh(context)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_delete_entity,))
