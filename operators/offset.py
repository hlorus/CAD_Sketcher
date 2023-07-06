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
from ..utilities.intersect import (
    get_intersections,
    get_offset_cb,
    get_offset_elements,
    get_offset_args,
    get_offset_elements_args,
    ElementTypes,
)
from ..model.utilities import get_connection_point
from .base_2d import Operator2d
from .utilities import ignore_hover


logger = logging.getLogger(__name__)


def _get_offset_co(point, normal, distance):
    # For start or endpoint: get point translated by distance along normal
    return point + normal * distance


def _bool_to_signed_int(invert):
    return -1 if invert else 1


def _inverted_dist(distance, invert):
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

    def init_main(self, context: Context):
        walker = EntityWalker(context.scene, self.sketch, entity=self.entity)
        path = walker.main_path()
        self.is_cyclic = walker.is_cyclic_path(path[0])

        entities, directions = path
        # self.entities = entities
        self.entity_indices = [e.slvs_index for e in entities]
        self.entities = [e.slvs_index for e in entities]

        self.directions = directions
        self.entity_count = len(self.entities)
        self.intersection_count = (
            self.entity_count if self.is_cyclic else self.entity_count - 1
        )

        if not path:
            return False

        # Store normals of start/endpoint
        start, end = walker.get_limitpoints(path)
        self.limitpoints = start, end
        self.co_start = start.co
        self.co_end = end.co
        self.nm_start = entities[0].normal(position=start.co)
        self.nm_end = entities[-1].normal(position=end.co)

        # Get connection points
        self.connection_points = []
        for i in range(self.intersection_count):
            neighbour_i = (i + 1) % self.entity_count
            self.connection_points.append(
                get_connection_point(entities[i], entities[neighbour_i])
            )

        self.offset_callbacks = [get_offset_cb(e) for e in entities]
        self.offset_args = [get_offset_args(e) for e in entities]
        self.centerpoints = [
            e.ct.slvs_index if not is_line(e) else None for e in entities
        ]
        print(self.entities)

        return True

    def main(self, context: Context):
        sketch = self.sketch
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
        entities = self.entities
        entity_indices = self.entity_indices
        directions = self.directions
        is_cyclic = self.is_cyclic
        entity_count = self.entity_count
        intersection_count = self.intersection_count

        point_coords = []
        for i in range(intersection_count):
            entity = entities[i]
            entity_dir = directions[i]
            neighbour_i = (i + 1) % entity_count
            neighbour = entities[neighbour_i]
            neighbour_dir = directions[neighbour_i]

            print(i, "intersect", entity, neighbour)

            # offset_cb_active = self.offset_callbacks[i]
            # offset_cb_neighbour = self.offset_callbacks[neighbour_i]

            point = self.connection_points[i]

            elems1 = get_offset_elements_args(
                ElementTypes.Line if is_line(entity) else ElementTypes.Sphere,
                _inverted_dist(distance, entity_dir),
                self.offset_args[i],
            )
            elems2 = get_offset_elements_args(
                ElementTypes.Line if is_line(neighbour) else ElementTypes.Sphere,
                _inverted_dist(distance, neighbour_dir),
                self.offset_args[neighbour_i],
            )

            intersections = sorted(
                get_intersections(
                    elems1,
                    elems2,
                    # get_offset_elements(entity, _inverted_dist(entity_dir)),
                    # get_offset_elements(neighbour, _inverted_dist(neighbour_dir)),
                ),
                key=lambda i: (i - point.co).length,
            )

            for coord in intersections:
                sse.add_point_2d(coord, sketch)

            if not intersections:
                return False

            intr = intersections[0]
            point_coords.append(intersections[0])

        points = [
            sse.add_point_2d(co, sketch, index_reference=True) for co in point_coords
        ]

        # Add start/endpoint if not cyclic
        if not is_cyclic:

            start, end = self.limitpoints
            start_co = _get_offset_co(
                self.co_start,
                self.nm_start,
                _inverted_dist(distance, directions[0]),
            )
            end_co = _get_offset_co(
                self.co_end,
                self.nm_end,
                _inverted_dist(distance, directions[-1]),
            )

            points.insert(0, sse.add_point_2d(start_co, sketch, index_reference=True))
            points.append(sse.add_point_2d(end_co, sketch, index_reference=True))

        # Exclude created points from selection
        [ignore_hover(p) for p in points]

        print(entities)

        # Create segments
        self.new_path = []
        for i, entity in enumerate(entities):
            direction = directions[i]

            i_start = (i - 1 if is_cyclic else i) % entity_count
            i_end = (i_start + 1) % len(points)
            p1 = points[i_start]
            p2 = points[i_end]

            use_construction = context.scene.sketcher.use_construction

            is_arc = not is_line(entity)
            add_func = sse.add_line_2d if not is_arc else sse.add_arc
            ct = self.centerpoints[i]
            args = (
                *((sketch.wp.nm.slvs_index, ct) if is_arc else ()),
                p1,
                p2,
            )
            kwargs = {
                "sketch": sketch,
                "construction": use_construction,
                "index_reference": True,
            }
            if is_arc:
                kwargs["invert"] = direction

            new_entity = add_func(*args, **kwargs)

            # new_entity = entity.new(
            #     context,
            #     p1=p1,
            #     p2=p2,
            #     sketch=sketch,
            #     **(
            #         {"invert": direction} if hasattr(entity, "invert_direction") else {}
            #     ),
            #     construction=use_construction,
            #     index_reference=True,
            # )
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
        #     if not is_line(new_entity):
        #         continue
        #     constraints.add_parallel(entity, new_entity, sketch=self.sketch)


register, unregister = register_stateops_factory((View3D_OT_slvs_add_offset,))
