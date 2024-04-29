import logging

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..model.types import SlvsPoint2D
from ..model.types import SlvsLine2D
from ..model.types import SlvsArc
from ..utilities.constants import HALF_TURN
from ..utilities.view import refresh
from ..solver import solve_system
from ..utilities.data_handling import is_entity_referenced
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_2d import Operator2d
from ..utilities.intersect import get_offset_elements, get_intersections

logger = logging.getLogger(__name__)


class View3D_OT_slvs_bevel(Operator, Operator2d):
    """Add a tangential arc between the two segments of a selected point"""

    bl_idname = Operators.Bevel
    bl_label = "Sketch Bevel"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(name="Radius")

    states = (
        state_from_args(
            "Point",
            description="Point to bevel",
            pointer="p1",
            types=(SlvsPoint2D,),
        ),
        state_from_args(
            "Radius",
            description="Radius of the bevel",
            property="radius",
            interactive=True,
        ),
    )

    def main(self, context):
        sketch = self.sketch
        sse = context.scene.sketcher.entities

        point = self.p1
        radius = self.radius

        # Get connected entities from point
        connected = []
        for e in (*sse.lines2D, *sse.arcs):
            # TODO: Priorize non_construction entities
            if point in e.connection_points():
                connected.append(e)

        if len(connected) != 2:
            self.report({"WARNING"}, "Point should have two connected segments")
            return False

        l1, l2 = connected
        self.connected = connected

        # If more than 1 intersection point, then sort them so we prioritise
        # the closest ones to the selected point.
        #   (Can happen with intersecting arcs)
        intersections = sorted(
            get_intersections(
                get_offset_elements(l1, radius),
                get_offset_elements(l1, -radius),
                get_offset_elements(l2, radius),
                get_offset_elements(l2, -radius),
                segment=True,
            ),
            key=lambda i: (i - self.p1.co).length,
        )

        coords = None
        for intersection in intersections:
            if hasattr(l1, "is_inside") and not l1.is_inside(intersection):
                continue
            if hasattr(l2, "is_inside") and not l2.is_inside(intersection):
                continue
            coords = intersection
            break

        if not coords:
            return False

        self.ct = sse.add_point_2d(coords, sketch)

        # Get tangent points
        p1_co, p2_co = l1.project_point(coords), l2.project_point(coords)

        if not all([co is not None for co in (p1_co, p2_co)]):
            return False

        self.points = (
            sse.add_point_2d(p1_co, sketch),
            sse.add_point_2d(p2_co, sketch),
        )

        # Get direction of arc
        connection_angle = l1.connection_angle(l2, connection_point=self.p1)
        invert = connection_angle < 0

        # Add Arc
        self.arc = sse.add_arc(sketch.wp.nm, self.ct, *self.points, sketch)
        self.arc.invert_direction = invert

        refresh(context)
        return True

    def fini(self, context, succeede):
        if not succeede:
            return

        sketch = self.sketch

        # Replace endpoints of existing segments
        point = self.p1
        p1, p2 = self.points

        seg1, seg2 = self.connected
        seg1.replace_point(point, p1)
        seg2.replace_point(point, p2)

        context.view_layer.update()

        # Add tangent constraints
        ssc = context.scene.sketcher.constraints
        ssc.add_tangent(self.arc, seg1, sketch)
        ssc.add_tangent(self.arc, seg2, sketch)

        # Remove original point if not referenced
        if not is_entity_referenced(point, context):
            context.scene.sketcher.entities.remove(point.slvs_index)
        else:
            # add reference construction lines and coincidents
            sse = context.scene.sketcher.entities
            for i in range(0, 2):
                if isinstance(self.connected[i], SlvsLine2D):
                    ssc.add_coincident(point, self.connected[i], sketch)
                    target = sse.add_line_2d(point, self.points[i], sketch)
                    target.construction = True
                elif isinstance(self.connected[i], SlvsArc):
                    target = sse.add_arc(sketch.wp.nm, self.connected[i].ct, self.points[i], point, sketch)
                    target.construction = True
                    if target.angle > HALF_TURN:
                        target.invert_direction = True

        refresh(context)
        solve_system(context)


register, unregister = register_stateops_factory((View3D_OT_slvs_bevel,))
