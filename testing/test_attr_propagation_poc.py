"""POC: custom attributes survive native conversion via domain-correct capture.

A per-segment ``CURVE`` attribute keeps its exact value through the identity
weld and the Fill Curve boundary, with no Sample Nearest / spatial transfer.

The failure this avoids: four segments of a closed loop carrying source values
10/20/30/40 collapsing to 15/25/35 at their shared corners, because Curve to
Mesh adapts a CURVE value onto points and Merge Points then averages the two
segment values meeting at each welded corner. Re-homing the value onto the EDGE
domain before the weld keeps every segment's value on its own edge, so nothing
is ever averaged.
"""

from .utils import Sketch2dTestCase

ATTR = "seg_val"
SEG_VALUES = (10, 20, 30, 40)


class TestAttributePropagationPOC(Sketch2dTestCase):
    def _build_square_loop(self):
        # Four segments sharing corners: a closed loop that fills to a face.
        pts = [
            self.add_point((0.0, 0.0)),
            self.add_point((1.0, 0.0)),
            self.add_point((1.0, 1.0)),
            self.add_point((0.0, 1.0)),
        ]
        return [
            self.add_line(pts[0], pts[1]),
            self.add_line(pts[1], pts[2]),
            self.add_line(pts[2], pts[3]),
            self.add_line(pts[3], pts[0]),
        ]

    def _assign_segment_values(self):
        """Give each segment (CURVE domain) a distinct source value."""
        from ..model.constants import SketchCurveType

        cd = self.sketch.data
        attr = cd.attributes.get(ATTR) or cd.attributes.new(ATTR, "INT", "CURVE")
        type_attr = cd.attributes["sketch_type"]
        line_indices = [
            i
            for i in range(len(cd.curves))
            if type_attr.data[i].value == SketchCurveType.LINE
        ]
        for value, idx in zip(SEG_VALUES, line_indices):
            attr.data[idx].value = value
        cd.update_tag()

    def _evaluated_attribute_values(self):
        """Read the converted mesh's ``seg_val`` values (Curves -> GN mesh)."""
        from ..utilities.curve_data import refresh_curve_geometry

        refresh_curve_geometry(self.sketch)
        self.context.view_layer.update()
        dg = self.context.evaluated_depsgraph_get()

        obj = self.sketch.target_object.original
        values = []
        for inst in dg.object_instances:
            if inst.object.original is not obj:
                continue
            try:
                mesh = inst.object.to_mesh()
            except RuntimeError:
                continue  # the Curves object itself has no mesh output
            attr = mesh.attributes.get(ATTR)
            if attr is not None:
                values = [int(d.value) for d in attr.data]
            inst.object.to_mesh_clear()
        return values

    def test_segment_values_survive_weld_and_fill(self):
        from ..utilities.convert_nodes import build_convert_node_group
        from ..utilities.curve_data import compute_merge_ids

        self._build_square_loop()
        self._assign_segment_values()
        compute_merge_ids(self.sketch)

        # Teach the one shared converter about the per-segment CURVE attribute.
        # This only rewires the small bridge section; no per-schema variant.
        build_convert_node_group(
            attribute_definitions=[{"name": ATTR, "type": "INT", "domain": "CURVE"}]
        )

        distinct = {v for v in self._evaluated_attribute_values() if v != 0}

        # Every source segment value survives the weld and the fill exactly.
        self.assertEqual(distinct, set(SEG_VALUES))
        # None of the corner-averaged artifacts the naive path would produce.
        self.assertTrue(distinct.isdisjoint({15, 25, 35}))
