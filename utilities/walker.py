import logging
from typing import List

from bpy.types import Scene

from ..model.types import SlvsGenericEntity

logger = logging.getLogger(__name__)


def point_entity_mapping(scene):
    """Get a entities per point mapping"""

    points = []
    entities = []
    for entity in scene.sketcher.entities.all:
        if entity.is_point():
            continue
        if not hasattr(entity, "connection_points"):
            continue
        for p in entity.connection_points():
            if not p.is_point():
                continue
            if p not in points:
                points.append(p)
            i = points.index(p)
            if i >= len(entities):
                entities.append([])
            ents = entities[i]
            if entity not in ents:
                ents.append(entity)
    assert len(points) == len(entities)
    return points, entities


def shares_point(seg_1, seg_2):
    points = seg_1.connection_points()
    for p in seg_2.connection_points():
        if p in points:
            return True
    return False


class EntityWalker:
    """
    Utility class to find connected entities

    Exposes:
        self.paths -> List of Tuples which hold a set of connected segment entities and their direction
    """

    def __init__(self, scene, sketch, entity=None):
        self.sketch_entities: List[SlvsGenericEntity] = []
        self.paths: List[tuple[List[SlvsGenericEntity, bool]]] = []
        self.scene: Scene = scene
        self.sketch = sketch
        self.points, self.entities = point_entity_mapping(scene)
        self.entity = entity

        # TODO: use sketch.entities?
        sketch_index = self.sketch.slvs_index
        for e in self.scene.sketcher.entities.all:
            if not hasattr(e, "sketch") or e.sketch_i != sketch_index:
                continue
            if not e.is_path():
                continue
            if e.construction:
                continue
            self.sketch_entities.append(e)

        self._run()

    @staticmethod
    def is_cyclic_path(path):
        if len(path) == 1:
            return path[0].is_closed()

        first, last = path[0], path[-1]

        # NOTE: first and last segment might be connected on one side only when there are 2 segments
        if len(path) == 2:
            return all(
                item in first.connection_points() for item in last.connection_points()
            )
        elif shares_point(first, last):
            return True
        return False

    @staticmethod
    def get_limitpoints(path):
        """Returns the start- and endpoint of a non-cyclic path or non if path is cyclic"""
        entities, directions = path

        return (
            entities[0].connection_points(direction=directions[0])[0],
            entities[-1].connection_points(direction=directions[-1])[1],
        )

    def _get_connected_entities(self, point):
        return self.entities[self.points.index(point)]

    def _branch_path(self):
        self.paths.append(([], []))
        return self.paths[-1]

    # TODO: rename ignore_point -> start_point / rename path -> spline_path
    def walker(self, entity, path, ignore_point=None, invert=False):
        segments = path[0]
        logger.debug(
            "goto: {} entrypoint: {} invert_walker {}".format(
                entity, ignore_point, invert
            )
        )

        if invert:
            # NOTE: this might be slow
            segments.insert(0, entity)
        else:
            segments.append(entity)

        self.sketch_entities.remove(entity)

        # Not great..
        if entity.is_closed():
            path[1].append(False)

        # NOTE: check through connecting points of entity
        # should respect all points that lie on actual geometry,
        # should also include coincident constraints

        points = list(
            filter(
                (lambda p: p.is_point() and p != ignore_point),
                entity.connection_points(),
            )
        )
        entities = []
        for point in points:
            ents = self._get_connected_entities(point)
            ents = filter((lambda e: e != entity and e in self.sketch_entities), ents)
            entities.append(ents)

        # NOTE: this should also invert and also happen if we can follow a segment from that point
        # point = next(points, None)
        point = points[0] if len(points) else None
        if point:
            invert_direction = entity.direction(
                (ignore_point if ignore_point else point),
                is_endpoint=(not ignore_point),
            )
            if invert:
                invert_direction = not invert_direction
                path[1].insert(0, invert_direction)
            else:
                path[1].append(invert_direction)

        for point, ents in zip(points, entities):
            # check through connected entities
            branch = False
            for e in ents:
                if branch:
                    path = self._branch_path()
                branch = True

                self.walker(e, path, ignore_point=point, invert=invert)

            # TODO: path could also split here...

            # Invert walker when there's a second connection point
            invert = not invert

    def _run(self):
        if self.entity is not None:
            self.walker(self.entity, self._branch_path())
            return

        while len(self.sketch_entities):
            start_entity = self.sketch_entities[0]
            logger.info("Start path walker at {}".format(start_entity))
            self.walker(start_entity, self._branch_path())

    def main_path(self):
        """Return the longest path, priorize closed paths"""

        paths = []
        for closed in (True, False):
            for path in self.paths:
                if self.is_cyclic_path(path[0]) == closed:
                    continue
            paths.append(path)

            paths.sort(key=lambda x: len(x[0]), reverse=True)
            if len(paths):
                return paths[0]
        return None
