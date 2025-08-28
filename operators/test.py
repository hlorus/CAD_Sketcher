from bpy.types import Operator
from bpy.utils import register_classes_factory

import unittest

class VIEW3D_OT_test(Operator):
    bl_idname = "view3d.slvs_test"
    bl_label = "Test"

    def execute(self, context):
        from ..testing import test_constraint_init, test_core, test_solver
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        suite.addTests(loader.loadTestsFromModule(test_solver))
        suite.addTests(loader.loadTestsFromModule(test_constraint_init))
        suite.addTests(loader.loadTestsFromModule(test_core))

        runner = unittest.TextTestRunner()
        runner.run(suite)

        return {"FINISHED"}


register, unregister = register_classes_factory((
    VIEW3D_OT_test,
))
