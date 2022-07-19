import logging

import bpy
from bpy.types import Context

from .. import class_defines

logger = logging.getLogger(__name__)


class Intersection:
    """Either a intersection between the segment to be trimmed and specified entity or a segment endpoint"""

    def __init__(self, element, co):
        # Either a intersecting entity, a segment endpoint or a coincident/midpoint constraint
        self.element = element
        self.co = co
        self.index = -1
        self._is_endpoint = False
        self._point = None

    def is_entity(self):
        return issubclass(type(self.element), class_defines.SlvsGenericEntity)

    def is_constraint(self):
        return issubclass(type(self.element), class_defines.GenericConstraint)

    def is_endpoint(self):
        return self._is_endpoint

    def get_point(self, context: Context):
        if self.is_entity() and self.element.is_point():
            return self.element
        if self.is_constraint():
            return self.element.entities()[0]
        if self._point == None:
            sketch = context.scene.sketcher.active_sketch
            # Implicitly create point at co
            self._point = context.scene.sketcher.entities.add_point_2d(self.co, sketch)

            # Add coincident constraint
            if self.is_entity():  # and self.element.is_segment()
                c = context.scene.sketcher.constraints.add_coincident(
                    self._point, self.element, sketch=sketch
                )

        return self._point

    def __str__(self):
        return "Intersection {}, {}, {}".format(self.index, self.co, self.element)


class TrimSegment:
    """Holds data of a segment to be trimmed"""

    def __init__(self, segment, pos):
        self.segment = segment
        self.pos = pos
        self._intersections = []
        self._is_closed = segment.is_closed()
        self.connection_points = segment.connection_points().copy()
        self.obsolete_intersections = []
        self.reuse_segment = False

        # Add connection points as intersections
        if not self._is_closed:
            for p in self.connection_points:
                intr = self.add(p, p.co)
                intr._is_endpoint = True

    def add(self, element, co):
        intr = Intersection(element, co)
        self._intersections.append(intr)
        return intr

    def check(self):
        relevant = self.relevant_intersections()
        return len(relevant) in (2, 4)

    def _sorted(self):
        # Return intersections sorted by distance from mousepos
        return sorted(
            self._intersections,
            key=lambda intr: self.segment.distance_along_segment(self.pos, intr.co),
        )

    def get_intersections(self):
        # Return intersections in order starting from startpoint
        sorted_intersections = self._sorted()
        for i, intr in enumerate(sorted_intersections):
            intr.index = i
        return sorted_intersections

    def relevant_intersections(self):
        # Get indices of two neighbouring points
        ordered = self.get_intersections()
        closest = ordered[0].index, ordered[-1].index

        # Form a list of relevant intersections, e.g. endpoints and closest points
        relevant = []
        for intr in ordered:
            if intr.is_endpoint():
                # Add endpoints
                if intr.index in closest:
                    # Not if next to trim segment
                    if intr not in self.obsolete_intersections:
                        self.obsolete_intersections.append(intr)
                    continue
                relevant.append(intr)

            if intr.index in closest:
                if intr.is_constraint():
                    if intr not in self.obsolete_intersections:
                        self.obsolete_intersections.append(intr)
                relevant.append(intr)

        def _get_log_msg():
            msg = "Trimming:"
            for intr in ordered:
                is_relevant = intr in relevant
                msg += "\n - " + ("RELEVANT " if is_relevant else "IGNORE ") + str(intr)
            return msg

        logger.debug(_get_log_msg())
        return relevant

    def ensure_points(self, context: Context):
        for intr in self.relevant_intersections():
            intr.get_point(context)

    def replace(self, context: Context):
        relevant = self.relevant_intersections()

        # Get constraints
        constrs = {}
        for c in context.scene.sketcher.constraints.all:
            entities = c.entities()
            if not self.segment in entities:
                continue
            constrs[c] = entities

        # Note: this seems to be needed, explicitly add all points and update viewlayer before starting to replace segments
        self.ensure_points(context)

        # NOTE: This is needed for some reason, otherwise there's a bug where
        # a point is suddenly interpreted as a line
        context.view_layer.update()

        # Create new segments
        segment_count = len(relevant) // 2
        for index, intrs in enumerate(
            [relevant[i * 2 : i * 2 + 2] for i in range(segment_count)]
        ):
            reuse_segment = index == 0 and not isinstance(
                self.segment, class_defines.SlvsCircle
            )
            intr_1, intr_2 = intrs
            if not intr_1:
                continue

            new_segment = self.segment.replace(
                context,
                intr_1.get_point(context),
                intr_2.get_point(context),
                use_self=reuse_segment,
            )

            if reuse_segment:
                self.reuse_segment = True
                continue

            # Copy constraints to new segment
            for c, ents in constrs.items():
                i = ents.index(self.segment)
                if index != 0:
                    if c.type in ("RATIO", "COINCIDENT", "MIDPOINT", "TANGENT"):
                        continue
                    ents[i] = new_segment
                    new_constr = c.copy(context, ents)
                else:
                    # if the original segment doesn't get reused the original constraints
                    # have to be remapped to the new segment
                    setattr(c, "entity{}_i".format(i + 1), new_segment.slvs_index)

        def _get_msg_obsolete():
            msg = "Remove obsolete intersections:"
            for intr in self.obsolete_intersections:
                msg += "\n - {}".format(intr)
            return msg

        logger.debug(_get_msg_obsolete())

        # Remove unused endpoints
        delete_constraints = []
        for intr in self.obsolete_intersections:
            if intr.is_constraint():
                c = intr.element
                i = context.scene.sketcher.constraints.get_index(c)
                # TODO: Make this a class reference
                bpy.ops.view3d.slvs_delete_constraint(type=c.type, index=i)
            if intr.is_entity():
                # Use operator which checks if other entities depend on this and auto deletes constraints
                # TODO: Make this a class reference
                bpy.ops.view3d.slvs_delete_entity(index=intr.element.slvs_index)

        # Remove original segment if not used
        if not self.reuse_segment:
            context.scene.sketcher.entities.remove(self.segment.slvs_index)