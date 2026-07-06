import logging

from bpy.types import Operator, Context

from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..curve_solver import solve_system
from ..model.curve_ref import PointRef, LineRef
from .base_2d import Operator2d
from .constants import types_point_2d
from .utilities import ignore_hover

logger = logging.getLogger(__name__)


class View3D_OT_slvs_add_rectangle(Operator, Operator2d):
    """Add a rectangle to the active sketch"""

    bl_idname = Operators.AddRectangle
    bl_label = "Add Rectangle"
    bl_options = {"REGISTER", "UNDO"}

    rect_state1_doc = ("Startpoint", "Pick or place starting point.")
    rect_state2_doc = ("Endpoint", "Pick or place ending point.")

    states = (
        state_from_args(
            rect_state1_doc[0],
            description=rect_state1_doc[1],
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            rect_state2_doc[0],
            description=rect_state2_doc[1],
            pointer="p2",
            types=types_point_2d,
            interactive=True,
            create_element="create_point",
        ),
    )

    def main(self, context: Context):
        sketch = self.sketch
        construction = context.scene.sketcher.use_construction

        p_lb, p_rt = self.get_point(context, 0), self.get_point(context, 1)

        # Create the two extra corner points
        p_rb = PointRef.create(sketch, (p_rt.co.x, p_lb.co.y), construction=construction)
        p_lt = PointRef.create(sketch, (p_lb.co.x, p_rt.co.y), construction=construction)

        if construction:
            p_lb.construction = True
            p_rt.construction = True

        # Create 4 lines
        points = (p_lb, p_rb, p_rt, p_lt)
        lines = []
        for i, start in enumerate(points):
            end = points[(i + 1) % 4]
            line = LineRef.create(sketch, start, end, construction=construction)
            lines.append(line)

        self.lines = lines

        for ref in (*points, *lines):
            ignore_hover(ref.curve_id)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "lines") and self.lines:
            sc = self.sketch.constraints
            for i, line_ref in enumerate(self.lines):
                func = sc.add_horizontal if (i % 2) == 0 else sc.add_vertical
                func(curve_id_1=line_ref.curve_id)

            data = self._state_data.get(1)
            if data.get("is_numeric_edit", False):
                input = data.get("numeric_input")

                startpoint = getattr(self, self.get_states()[0].pointer)
                sp_cid = startpoint.curve_id if hasattr(startpoint, 'curve_id') else ""
                for val, line_ref in zip(input, (self.lines[1], self.lines[2])):
                    if val is None:
                        continue
                    sc.add_distance(
                        init=True,
                        curve_id_1=sp_cid,
                        curve_id_2=line_ref.curve_id,
                    )

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)
            self.sketch.geometry_solved = False

    def create_point(self, context: Context, values, state, state_data):
        value = values[0]

        if state_data.get("is_numeric_edit", False):
            data = self._state_data.get(1)
            input = data.get("numeric_input")
            # use relative coordinates
            orig = getattr(self, self.get_states()[0].pointer).co

            for i, val in enumerate(input):
                if val is None:
                    continue
                value[i] = orig[i] + val

        construction = context.scene.sketcher.use_construction

        ref = PointRef.create(self.sketch, value, construction=construction)
        cid = ref.curve_id
        state_data["curve_id"] = cid
        ignore_hover(cid)

        self.add_coincident(context, ref, state, state_data)
        state_data["type"] = PointRef
        return cid


register, unregister = register_stateops_factory((View3D_OT_slvs_add_rectangle,))
