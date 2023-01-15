import glob
from pathlib import Path
from CAD_Sketcher.testing.utils import BgsTestCase

class TestConstraints(BgsTestCase):
    def test_constraints(self):
        import bpy
        path = str(Path(__file__).parent.absolute() / "constraints" / "*.blend")
        test_files = glob.glob(path)
        for test_file in test_files:
            with bpy.data.libraries.load(test_file) as (data_from, data_to):
                for attr in dir(data_to):
                    setattr(data_to, attr, getattr(data_from, attr))
                ok = self.context.scene.sketcher.solve(self.context)
                self.assertTrue(ok)
