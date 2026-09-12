"""Tests for the entity type icons shown in the entities list.

The icons are loose PNGs resolved by name, so a renamed or missing file fails
silently (the row simply loses its icon). These tests pin the naming contract.
"""

from unittest import TestCase

from .. import icon_manager
from ..model.constants import SketchCurveType

TYPES = (
    SketchCurveType.POINT,
    SketchCurveType.LINE,
    SketchCurveType.ARC,
    SketchCurveType.CIRCLE,
)
NAMES = ("POINT", "LINE", "ARC", "CIRCLE")


class TestEntityIcons(TestCase):
    def test_every_type_ships_both_variants(self):
        for name in NAMES:
            for file in (f"ENTITY_{name}.png", f"ENTITY_{name}_CONSTRUCTION.png"):
                path = icon_manager.get_folder_path() / file
                self.assertTrue(path.exists(), f"missing icon: {file}")

    def test_each_type_and_variant_maps_to_its_own_icon(self):
        names = [
            icon_manager.get_entity_icon_name(type, construction)
            for type in TYPES
            for construction in (False, True)
        ]

        self.assertTrue(all(names), "an entity type resolved to no icon")
        self.assertEqual(len(set(names)), len(names), "two variants share an icon")

    def test_every_icon_is_loaded(self):
        # Background Blender never calls load(), so load the previews here and
        # leave the module as it was found (interactive runs have them loaded).
        was_loaded = icon_manager.preview_icons is not None
        icon_manager.load_preview_icons()
        try:
            for type in TYPES:
                for construction in (False, True):
                    name = icon_manager.get_entity_icon_name(type, construction)
                    self.assertIsNotNone(icon_manager.preview_icons.get(name), name)
        finally:
            if not was_loaded:
                icon_manager.unload_preview_icons()

    def test_unknown_type_falls_back_to_no_icon(self):
        self.assertEqual(icon_manager.get_entity_icon_name(-1), "")
        self.assertEqual(icon_manager.get_entity_icon(-1), 0)
