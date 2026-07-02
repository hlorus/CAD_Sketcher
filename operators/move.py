from bpy.types import Operator, Context, Event
from ..model.sketch_ref import get_active_sketch
from mathutils import Vector
from bpy.props import FloatVectorProperty

from .. import global_data
from ..declarations import Operators
from ..model.curve_ref import curve_ref, PointRef
from .base_2d import Operator2d
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..curve_solver import solve_system
from ..utilities.curve_data import refresh_curve_geometry, batch_update
from ..utilities.view import get_pos_2d


def get_points(context: Context):
    """Return PointRefs for all selected points + points of selected lines/arcs."""
    sketch = get_active_sketch(context)
    if not sketch:
        return []

    point_cids = set()

    for cid in global_data.selected:
        ref = curve_ref(sketch, cid)
        if not ref.valid:
            continue

        if isinstance(ref, PointRef):
            point_cids.add(cid)
        else:
            # Collect relationship points
            for attr in ("start_point_id", "end_point_id", "center_point_id"):
                pt_cid = ref._get_attr_value(attr, 0)
                if pt_cid:
                    point_cids.add(pt_cid)

    return [PointRef(sketch, cid) for cid in point_cids]


class View3D_OT_slvs_move(Operator, Operator2d):
    """Move selected entities around, independent of constraints"""

    bl_idname = Operators.Move
    bl_label = "Move Entities"
    bl_options = {"UNDO", "REGISTER"}

    offset: FloatVectorProperty(
        name="Offset", subtype="COORDINATES", size=2, options={"SKIP_SAVE"}
    )

    states = (
        state_from_args(
            "Offset",
            description="Offset vector to apply to the selection of entities",
            property="offset",
            state_func="get_offset",
            interactive=True,
        ),
    )

    def invoke(self, context: Context, event: Event):
        coords = Vector((event.mouse_region_x, event.mouse_region_y))
        retval = super().invoke(context, event)
        self.origin_coords = get_pos_2d(context, self._get_wp(), coords)
        return retval

    def get_offset(self, context: Context, coords):
        wp = self._get_wp()
        pos = get_pos_2d(context, wp, coords)
        if pos is None:
            return None
        return Vector(pos) - self.origin_coords

    def main(self, context: Context):
        sketch = self.sketch
        points = get_points(context)

        with batch_update(self.sketch):
            for point in points:
                point.co = point.co + self.offset
        return {"FINISHED"}

    def fini(self, context: Context, succeede: bool):
        if succeede:
            if self.sketch:
                self.sketch.geometry_solved = False
            solve_system(context, sketch=self.sketch)
            refresh_curve_geometry(self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_move,))
