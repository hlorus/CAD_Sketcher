import logging

logger = logging.getLogger(__name__)

from . import class_defines


def point_entity_mapping(scene):

    # Get a entities per point mapping
    points = []
    entities = []
    for entity in scene.sketcher.entities.all:
        if type(entity) in class_defines.point:
            continue
        if not hasattr(entity, "connection_points"):
            continue
        for p in entity.connection_points():
            if type(p) not in class_defines.point:
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


# TODO: make generic path creator class?
class BezierConvertor:
    def __init__(self, scene, sketch):
        self.sketch_entities = []
        self.paths = []
        self.ok = True
        self.scene = scene
        self.sketch = sketch
        self.points, self.entities = point_entity_mapping(scene)

        # TODO: use sketch.entities?
        sketch_index = self.sketch.slvs_index
        for e in self.scene.sketcher.entities.all:
            if not hasattr(e, "sketch") or e.sketch_i != sketch_index:
                continue
            if isinstance(e, class_defines.SlvsPoint2D):
                continue
            if e.construction:
                continue
            self.sketch_entities.append(e)

    def _get_connected_entities(self, point):
        return self.entities[self.points.index(point)]

    def _branch_path(self):
        self.paths.append(([], []))
        return self.paths[-1]

    # TODO: rename ignore_point -> start_point / rename path -> spline_path
    def walker(self, entity, path, ignore_point=None, invert=False):
        segments = path[0]
        logger.debug("goto: {} entrypoint: {} invert_walker {}".format(entity, ignore_point, invert))

        if invert:
            # NOTE: this might be slow
            segments.insert(0, entity)
        else:
            segments.append(entity)

        self.sketch_entities.remove(entity)

        # Not great..
        if isinstance(entity, class_defines.SlvsCircle):
            path[1].append(False)

        # NOTE: check through connecting points of entity
        # should respect all points that lie on actual geometry,
        # should also include coincident constraints

        points = list(
            filter(
                (
                    lambda p: isinstance(p, class_defines.SlvsPoint2D)
                    and p != ignore_point
                ),
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

    def run(self):
        while len(self.sketch_entities):
            start_entity = self.sketch_entities[0]
            logger.info("Start path walker at {}".format(start_entity))
            self.walker(start_entity, self._branch_path())

        # TODO: check path, set self.ok

    @staticmethod
    def shares_point(seg_1, seg_2):
        points = seg_1.connection_points()
        for p in seg_2.connection_points():
            if p in points:
                return True
        return False

    def is_cyclic_path(self, path):
        if len(path) == 1:
            return isinstance(path[0], class_defines.SlvsCircle)

        first, last = path[0], path[-1]

        # NOTE: first and last segment might be connected on one side only when there are 2 segments..
        if len(path) == 2:
            return all(
                item in first.connection_points() for item in last.connection_points()
            )
        elif self.shares_point(first, last):
            return True
        return False

    def to_bezier(self, curve_data):
        curve_data.fill_mode = "FRONT" if self.sketch.fill_shape else "NONE"

        for spline_path in self.paths:
            path_segments = spline_path[0]
            s = curve_data.splines.new("BEZIER")

            is_cyclic = self.is_cyclic_path(path_segments)
            if is_cyclic:
                s.use_cyclic_u = True

            segment_count = [
                seg.bezier_segment_count()
                if hasattr(seg, "bezier_segment_count")
                else 1
                for seg in path_segments
            ]
            amount = sum(segment_count)

            if not is_cyclic:
                amount += 1
            # NOTE: There's  already one point in a new spline
            s.bezier_points.add(amount - 1)

            startpoint = s.bezier_points[0]
            class_defines.set_handles(startpoint)
            previous_point = startpoint

            last_index = len(path_segments) - 1
            index = 0
            for i, segment in enumerate(path_segments):
                invert_direction = spline_path[1][i]

                # TODO: rename to seg_count and segment_counts
                sub_segment_count = segment_count[i]

                if i == last_index and is_cyclic:
                    end = s.bezier_points[0]
                else:
                    end = s.bezier_points[index + sub_segment_count]

                midpoints = (
                    [
                        s.bezier_points[index + i + 1]
                        for i in range(sub_segment_count - 1)
                    ]
                    if sub_segment_count
                    else []
                )
                kwargs = {}
                if i == 0:
                    kwargs["set_startpoint"] = True
                if sub_segment_count > 1:
                    kwargs["midpoints"] = midpoints

                previous_point = segment.to_bezier(
                    s, previous_point, end, invert_direction, **kwargs
                )
                index += sub_segment_count
