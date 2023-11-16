import logging
import math

from bpy.types import Operator, Context
from bpy.props import FloatProperty

from ..model.categories import SEGMENT
from ..model.identifiers import is_line, is_circle
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from ..utilities.view import refresh
from ..utilities.walker import EntityWalker
from ..utilities.intersect import get_offset_elements, get_intersections
from ..model.utilities import get_connection_point
from .base_2d import Operator2d
from .utilities import ignore_hover


logger = logging.getLogger(__name__)


def _get_offset_co(point, normal, distance):
    # For start or endpoint: get point translated by distance along normal
    return point.co + normal * distance


def _bool_to_signed_int(invert):
    return -1 if invert else 1

def _inverted_dist(invert, distance):
    sign = _bool_to_signed_int(invert) * _bool_to_signed_int(distance < 0)
    return math.copysign(distance, sign)


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
            use_create=False,
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

        ignore_hover(entity)

        if is_circle(entity):
            c_new = entity.new(context, radius=entity.radius + distance)
            ignore_hover(c_new)

            refresh(context)
            return True


        walker = EntityWalker(context.scene, sketch, entity=entity)
        path = walker.main_path()
        is_cyclic = walker.is_cyclic_path(path[0])

        if path is None:
            return False

        # Get intersections and create points
        points = []
        entities, directions = path
        self.entities = entities

        intersection_count = len(entities) if is_cyclic else len(entities) - 1
        point_coords = []
        for i in range(intersection_count):
            entity = entities[i]
            entity_dir = directions[i]
            neighbour_i = (i + 1) % len(entities)
            neighbour = entities[neighbour_i]
            neighbour_dir = directions[neighbour_i]
            point = get_connection_point(entity, neighbour)

            intersections = sorted(
                get_intersections(
                    get_offset_elements(entity, _inverted_dist(entity_dir, distance)),
                    get_offset_elements(neighbour, _inverted_dist(neighbour_dir, distance)),
                ),
                key=lambda i: (i - point.co).length,
            )

            if not intersections:
                return False

            intr = intersections[0]
            point_coords.append(intersections[0])

        points = [
            sse.add_point_2d(co, sketch, index_reference=True) for co in point_coords
        ]

        # Add start/endpoint if not cyclic
        if not is_cyclic:

            start, end = walker.get_limitpoints(path)
            start_co = _get_offset_co(
                start,
                entities[0].normal(position=start.co),
                _inverted_dist(directions[0], distance),
            )
            end_co = _get_offset_co(
                end,
                entities[-1].normal(position=end.co),
                _inverted_dist(directions[-1], distance),
            )

            points.insert(0, sse.add_point_2d(start_co, sketch, index_reference=True))
            points.append(sse.add_point_2d(end_co, sketch, index_reference=True))

        # Exclude created points from selection
        [ignore_hover(p) for p in points]

        # Create segments
        self.new_path = []
        for i, entity in enumerate(entities):
            direction = directions[i]

            i_start = (i - 1 if is_cyclic else i) % len(entities)
            i_end = (i_start + 1) % len(points)
            p1 = points[i_start]
            p2 = points[i_end]

            use_construction = context.scene.sketcher.use_construction
            new_entity = entity.new(
                context,
                p1=p1,
                p2=p2,
                sketch=sketch,
                **(
                    {"invert": direction} if hasattr(entity, "invert_direction") else {}
                ),
                construction=use_construction,
                index_reference=True,
            )
            ignore_hover(new_entity)

            self.new_path.append(new_entity)

        refresh(context)
        return True

    def fini(self, context: Context, succeede: bool):
        if not succeede:
            return

        constraints = context.scene.sketcher.constraints

        # Add parallel constraint
        # for entity, new_entity in zip(self.entities, self.new_path):
        #     if not is_line(entity):
        #         continue
        #     constraints.add_parallel(entity, new_entity, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_offset,))
