from .utils import BgsTestCase
from ..serialize import scene_to_dict


class TestPolylineNaming(BgsTestCase):
    def test_polyline_names_are_unique_across_sketches(self):
        self.entities.ensure_origin_elements(self.context)
        workplane = self.entities.origin_plane_XY

        first_sketch = self.entities.add_sketch(workplane)
        second_sketch = self.entities.add_sketch(workplane)

        first_segments = self._create_segments(first_sketch, ((0, 0), (1, 0), (1, 1)))
        second_segments = self._create_segments(second_sketch, ((2, 0), (3, 0), (3, 1)))

        first_polyline = self.entities.add_polyline(first_segments, False, first_sketch)
        second_polyline = self.entities.add_polyline(
            second_segments, False, second_sketch
        )

        self.assertEqual(first_polyline.name, "Polyline 1")
        self.assertEqual(second_polyline.name, "Polyline 2")

        polylines = scene_to_dict(self.scene)["entities"]["polylines"]
        self.assertEqual(polylines[0]["name"], "Polyline 1")
        self.assertEqual(polylines[1]["name"], "Polyline 2")

    def _create_segments(self, sketch, coordinates):
        points = [self.entities.add_point_2d(co, sketch) for co in coordinates]
        return [
            self.entities.add_line_2d(start, end, sketch).slvs_index
            for start, end in zip(points, points[1:])
        ]
