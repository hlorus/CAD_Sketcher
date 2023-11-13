import logging

from bpy.types import Operator, Context

from ..model.types import SlvsPoint2D
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..solver import solve_system
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
        sse = context.scene.sketcher.entities

        p1, p2 = self.get_point(context, 0), self.get_point(context, 1)
        p_lb, p_rt = p1, p2

        p_rb = sse.add_point_2d((p_rt.co.x, p_lb.co.y), sketch)
        p_lt = sse.add_point_2d((p_lb.co.x, p_rt.co.y), sketch)

        if context.scene.sketcher.use_construction:
            p_lb.construction = True
            p_rb.construction = True
            p_rt.construction = True
            p_lt.construction = True

        lines = []
        points = (p_lb, p_rb, p_rt, p_lt)
        for i, start in enumerate(points):
            end = points[i + 1 if i < len(points) - 1 else 0]

            line = sse.add_line_2d(start, end, sketch)
            if context.scene.sketcher.use_construction:
                line.construction = True
            lines.append(line)

        self.lines = lines

        for e in (*points, *lines):
            ignore_hover(e)
        return True

    def fini(self, context: Context, succeede: bool):
        if hasattr(self, "lines") and self.lines:
            ssc = context.scene.sketcher.constraints
            for i, line in enumerate(self.lines):
                func = ssc.add_horizontal if (i % 2) == 0 else ssc.add_vertical
                func(line, sketch=self.sketch)

            data = self._state_data.get(1)
            if data.get("is_numeric_edit", False):
                input = data.get("numeric_input")

                # constrain distance
                startpoint = getattr(self, self.get_states()[0].pointer)
                for val, line in zip(input, (self.lines[1], self.lines[2])):
                    if val is None:
                        continue
                    ssc.add_distance(
                        startpoint,
                        line,
                        sketch=self.sketch,
                        init=True,
                    )

        if succeede:
            if self.has_coincident():
                solve_system(context, sketch=self.sketch)

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

        sse = context.scene.sketcher.entities
        point = sse.add_point_2d(value, self.sketch)
        ignore_hover(point)
        if context.scene.sketcher.use_construction:
            point.construction = True

        self.add_coincident(context, point, state, state_data)
        state_data["type"] = SlvsPoint2D
        return point.slvs_index


register, unregister = register_stateops_factory((View3D_OT_slvs_add_rectangle,))
