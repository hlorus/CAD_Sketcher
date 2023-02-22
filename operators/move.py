from bpy.types import Operator, Context, Event
from mathutils import Vector
from bpy.props import FloatVectorProperty

from ..declarations import Operators
from .base_2d import Operator2d
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.data_handling import get_flat_deps
from ..solver import solve_system
from ..utilities.view import get_pos_2d


def get_points(context: Context):
    """Return a list of points that are either selected or a dependency of a selected entity"""
    entities = context.scene.sketcher.entities.selected_active
    points = []

    def add(p):
        if p in points:
            return
        points.append(p)

    def is_point2d(e):
        if not e.is_2d():
            return False
        if not e.is_point():
            return False
        return True

    for entity in entities:
        if not entity:
            continue
        if is_point2d(entity):
            add(entity)
            continue

        dependencies = get_flat_deps(entity)
        for e in dependencies:
            if not is_point2d(e):
                continue

            add(e)
    return points


# NOTE: Only 2D for now
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
        self.origin_coords = get_pos_2d(context, self.sketch.wp, coords)
        return retval

    def get_offset(self, context: Context, coords):
        wp = self.sketch.wp
        pos = get_pos_2d(context, wp, coords)
        if pos is None:
            return None

        delta = Vector(pos) - self.origin_coords
        return delta

    def main(self, context: Context):
        points = get_points(context)

        for point in points:
            if point.fixed:
                continue

            point.co += self.offset

        return {"FINISHED"}

    def fini(self, context: Context, succeede: bool):
        if succeede:
            solve_system(context, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_move,))
