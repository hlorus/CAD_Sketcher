import logging
import math

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..model.categories import SEGMENT
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_2d import Operator2d
from ..utilities.walker import EntityWalker
from ..utilities.intersect import get_offset_elements, get_intersections
from ..model.utilities import get_connection_point


logger = logging.getLogger(__name__)


def _get_offset_co(point, normal, distance):
    # For start or endpoint: get point translated by distance along normal
    return point.co + normal * distance


class View3D_OT_slvs_add_offset(Operator, Operator2d):
    """Copy and offset selected entities along with their constraints by the distance value"""

    bl_idname = Operators.Offset
    bl_label = "Offset"
    bl_options = {"REGISTER", "UNDO"}

    distance: FloatProperty(name="Distance")

    states = (
        state_from_args(
            "Entity",
            description="Base entity to get path from",
            pointer="entity",
            types=SEGMENT,
        ),
        state_from_args(
            "Distance",
            description="Distance to offset the created entities",
            property="distance",
            interactive=True,
        ),
    )

    def main(self, context: Context):
        sketch = self.sketch
        entity = self.entity
        distance = self.distance
        sse = context.scene.sketcher.entities

        walker = EntityWalker(context.scene, sketch, entity=entity)
        path = walker.main_path()
        is_cyclic = walker.is_cyclic_path(path[0])

        if path is None:
            return False

        # Get intersections and create points
        points = []
        entities, directions = path

        intersection_count = len(entities) if is_cyclic else len(entities) - 1
        point_coords = []
        for i in range(intersection_count):
            entity = entities[i]
            entity_dir = directions[i]
            neighbour_i = (i + 1) % len(entities)
            neighbour = entities[neighbour_i]
            neighbour_dir = directions[neighbour_i]
            point = get_connection_point(entity, neighbour)

            def _bool_to_signed_int(invert):
                return -1 if invert else 1

            def _inverted_dist(invert):
                sign = _bool_to_signed_int(invert) * _bool_to_signed_int(distance < 0)
                return math.copysign(distance, sign)

            intersections = sorted(
                get_intersections(
                    get_offset_elements(entity, _inverted_dist(entity_dir)),
                    get_offset_elements(neighbour, _inverted_dist(neighbour_dir)),
                ),
                key=lambda i: (i - point.co).length,
            )

            if not intersections:
                return False

            intr = intersections[0]
            point_coords.append(intersections[0])

        points = [sse.add_point_2d(co, sketch) for co in point_coords]

        # Add start/endpoint if not cyclic
        if not is_cyclic:

            start, end = walker.get_limitpoints(path)
            start_co = _get_offset_co(
                start,
                entities[0].normal(position=start.co),
                _inverted_dist(directions[0]),
            )
            end_co = _get_offset_co(
                end,
                entities[-1].normal(position=end.co),
                _inverted_dist(directions[-1]),
            )

            points.insert(0, sse.add_point_2d(start_co, sketch))
            points.append(sse.add_point_2d(end_co, sketch))

        # Create segments
        for i, entity in enumerate(entities):
            direction = directions[i]

            i_start = (i - 1 if is_cyclic else i) % len(entities)
            i_end = (i_start + 1) % len(points)
            p1 = points[i_start]
            p2 = points[i_end]

            entity.from_props(context, start=p1, end=p2, invert=direction)

        return True


register, unregister = register_stateops_factory((View3D_OT_slvs_add_offset,))
