from unittest import TestCase

from ..ui.pie_menu import PIE_MENU_ID, PIE_SHORTCUT, VIEW3D_MT_slvs_pie


class TestPieMenu(TestCase):
    def test_identifier_and_shortcut(self):
        self.assertEqual(VIEW3D_MT_slvs_pie.bl_idname, PIE_MENU_ID)
        self.assertEqual(PIE_SHORTCUT, ("M", True, True))
