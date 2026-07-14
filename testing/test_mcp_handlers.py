from testing.utils import Sketch2dTestCase

from ..mcp import handlers


class TestMcpHandlers(Sketch2dTestCase):
    def test_status_and_list(self):
        status = handlers.get_sketcher_status(self.context)
        self.assertIn("active_sketch_i", status)
        self.assertIn("sketch_count", status)

        listed = handlers.list_sketches(self.context)
        self.assertGreaterEqual(len(listed["sketches"]), 1)

    def test_create_line_distance_solve(self):
        sketch = self.sketch
        sk_i = sketch.slvs_index

        p1 = handlers.add_point_2d(self.context, co=(0.0, 0.0), sketch_i=sk_i, fixed=True)
        p2 = handlers.add_point_2d(self.context, co=(10.0, 5.0), sketch_i=sk_i)
        line = handlers.add_line_2d(
            self.context, p1_i=p1["index"], p2_i=p2["index"], sketch_i=sk_i
        )
        handlers.add_horizontal(self.context, entity1_i=line["index"], sketch_i=sk_i)
        handlers.add_distance(
            self.context,
            entity1_i=p1["index"],
            entity2_i=p2["index"],
            value=20.0,
            sketch_i=sk_i,
        )

        result = handlers.solve(self.context, sketch_i=sk_i)
        self.assertTrue(result["ok"])

        ents = handlers.list_entities(self.context, sketch_i=sk_i)
        self.assertGreaterEqual(len(ents["entities"]), 3)

        cons = handlers.list_constraints(self.context, sketch_i=sk_i)
        self.assertGreaterEqual(len(cons["constraints"]), 2)

    def test_dispatch_envelope(self):
        resp = handlers.dispatch(
            {"type": "get_sketcher_status", "params": {}}, context=self.context
        )
        self.assertEqual(resp["status"], "success")
        self.assertIn("result", resp)

        bad = handlers.dispatch({"type": "no_such_command", "params": {}}, context=self.context)
        self.assertEqual(bad["status"], "error")

    def test_add_sketch_handler(self):
        created = handlers.add_sketch(self.context, name="MCP_Sketch", activate=True)
        self.assertEqual(created["type"], "SlvsSketch")
        self.assertEqual(self.sketcher.active_sketch_i, created["index"])
