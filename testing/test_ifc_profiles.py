"""Receive IFC exports of the retained Part document through the native operator.

IfcOpenShell is optional for CAD Sketcher; these integration cases run when it
is installed in Blender's Python environment. They reuse the existing authored
.blend file and compare the reopened IFC to its native curves, not to exporter
intermediates.
"""

import math
import tempfile
import unittest
from pathlib import Path

import bpy
from mathutils import Matrix

from ..model.curve_ref import curve_ref
from ..model.sketch_ref import get_sketches, set_active_sketch
from ..utilities.curve_data import read_uuid_list
from ..utilities.ifc_file import write_sketch_profiles
from ..utilities.ifc_sketch import sketch_profiles
from ..utilities.preferences import get_prefs

try:
    import ifcopenshell
    import ifcopenshell.validate
except ImportError:
    ifcopenshell = None

FIXTURE = Path(__file__).parent / "fixtures" / "CAD_Sketcher_Part.blend"
HOLES = {
    "Back Plate A Sketch": 3,
    "Base Plate Sketch": 2,
    "Pipe Sketch": 1,
    "Top Notch Add Sketch": 0,
    "Top Nothc Subtract Sketch": 0,
    "Sketch Sketch": 0,
}


def _close(first: tuple, second: tuple, tolerance: float = 1e-8) -> bool:
    return len(first) == len(second) and all(
        abs(a - b) <= tolerance for a, b in zip(first, second)
    )


def _circle_point(circle, parameter: float) -> tuple[float, float]:
    placement = circle.Position
    center = placement.Location.Coordinates
    direction = placement.RefDirection
    rotation = math.atan2(*reversed(direction.DirectionRatios)) if direction else 0.0
    angle = rotation + parameter
    return (
        center[0] + circle.Radius * math.cos(angle),
        center[1] + circle.Radius * math.sin(angle),
    )


@unittest.skipIf(ifcopenshell is None, "IfcOpenShell is an optional export dependency")
class TestIFCProfiles(unittest.TestCase):
    """Exercise actual migrated sketch data, saved IFC bytes and rejection."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the native document once; each case restores its own edits."""
        bpy.ops.wm.open_mainfile(filepath=str(FIXTURE))
        if bpy.ops.view3d.slvs_migrate_legacy() != {"FINISHED"}:
            raise RuntimeError("The retained Part document did not migrate")
        cls.sketches = list(get_sketches(bpy.context))
        cls.scale = bpy.context.scene.unit_settings.scale_length

    def setUp(self) -> None:
        """Enable export explicitly and give each case an isolated destination."""
        self.assertEqual({sketch.name for sketch in self.sketches}, set(HOLES))
        self.assertAlmostEqual(self.scale, 0.001, places=9)
        prefs = get_prefs()
        previous = prefs.enable_ifc_profile_export
        self.addCleanup(setattr, prefs, "enable_ifc_profile_export", previous)
        prefs.enable_ifc_profile_export = True
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    @classmethod
    def tearDownClass(cls) -> None:
        """Restore the fixture-migration suite's empty, unsaved-file boundary."""
        bpy.ops.wm.read_homefile(use_empty=True)

    def _native(self, sketch) -> dict:
        result = {"lines": [], "arcs": [], "circles": []}

        def scaled(point):
            return tuple(float(axis) * self.scale for axis in point)

        for cid in read_uuid_list(sketch.data, "curve_id"):
            if not cid:
                continue
            ref = curve_ref(sketch, cid)
            if ref.is_point() or ref.construction:
                continue
            if ref.is_line():
                result["lines"].append((scaled(ref.p1.co), scaled(ref.p2.co)))
            else:
                circle = (scaled(ref.ct.co), float(ref.radius) * self.scale)
                if ref.is_circle():
                    result["circles"].append(circle)
                else:
                    self.assertTrue(ref.is_arc())
                    middle = float(ref.start_angle) + float(ref.angle) / 2
                    result["arcs"].append(
                        {
                            "circle": circle,
                            "start": scaled(ref.p1.co),
                            "end": scaled(ref.p2.co),
                            "middle": (
                                circle[0][0] + circle[1] * math.cos(middle),
                                circle[0][1] + circle[1] * math.sin(middle),
                            ),
                            "sweep": float(ref.angle),
                        }
                    )
        return result

    def _reopen(self, path: Path):
        document = ifcopenshell.open(str(path))
        self.assertEqual(document.schema, "IFC4")
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(document, logger, express_rules=True)
        self.assertEqual(logger.statements, [])
        for project in document.by_type("IfcContext"):
            self.assertEqual(
                {(unit.UnitType, unit.Name) for unit in project.UnitsInContext.Units},
                {("LENGTHUNIT", "METRE"), ("PLANEANGLEUNIT", "RADIAN")},
            )
        self.assertEqual(
            document.by_type("IfcGeometricRepresentationContext")[0].Precision, 1e-8
        )
        return document

    def _receive_geometry(self, document, native: dict) -> None:
        lines = [
            (tuple(a.Coordinates), tuple(b.Coordinates))
            for curve in document.by_type("IfcPolyline")
            for a, b in zip(curve.Points, curve.Points[1:])
        ]
        self.assertEqual(len(lines), len(native["lines"]))
        for expected in native["lines"]:
            match = next(
                (
                    actual
                    for actual in lines
                    if all(_close(a, b) for a, b in zip(actual, expected))
                    or all(_close(a, b) for a, b in zip(reversed(actual), expected))
                ),
                None,
            )
            self.assertIsNotNone(match, expected)
            lines.remove(match)

        trims = list(document.by_type("IfcTrimmedCurve"))
        self.assertEqual(len(trims), len(native["arcs"]))
        for expected in native["arcs"]:
            matches = []
            for trim in trims:
                circle = trim.BasisCurve
                self.assertTrue(circle.is_a("IfcCircle"))
                if not _close(
                    tuple(circle.Position.Location.Coordinates), expected["circle"][0]
                ):
                    continue
                if abs(circle.Radius - expected["circle"][1]) > 1e-10:
                    continue
                self.assertEqual(trim.MasterRepresentation, "PARAMETER")
                start, end = trim.Trim1[0].wrappedValue, trim.Trim2[0].wrappedValue
                # Decode the IFC traversal. A reversed boundary must preserve
                # the native arc's midpoint, not choose the complementary arc.
                direction = 1 if trim.SenseAgreement else -1
                span = direction * ((direction * (end - start)) % math.tau)
                points = [_circle_point(circle, start + span * t) for t in (0, 0.5, 1)]
                forward = _close(points[0], expected["start"]) and _close(
                    points[2], expected["end"]
                )
                backward = _close(points[0], expected["end"]) and _close(
                    points[2], expected["start"]
                )
                if forward or backward:
                    self.assertTrue(_close(points[1], expected["middle"]))
                    self.assertAlmostEqual(
                        span, expected["sweep"] * (1 if forward else -1), places=10
                    )
                    matches.append(trim)
            self.assertEqual(len(matches), 1)
            trims.remove(matches[0])

        arc_bases = {
            curve.BasisCurve.id() for curve in document.by_type("IfcTrimmedCurve")
        }
        circles = [
            curve
            for curve in document.by_type("IfcCircle")
            if curve.id() not in arc_bases
        ]
        self.assertEqual(len(circles), len(native["circles"]))
        for center, radius in native["circles"]:
            match = next(
                (
                    c
                    for c in circles
                    if _close(tuple(c.Position.Location.Coordinates), center)
                    and abs(c.Radius - radius) <= 1e-10
                ),
                None,
            )
            self.assertIsNotNone(match, (center, radius))
            circles.remove(match)

    def test_retained_part_roundtrip_keeps_curves_voids_and_units(self) -> None:
        """All six native profiles survive export, including clockwise arc trims."""
        combined = []
        negative_trims = 0
        for sketch in self.sketches:
            with self.subTest(sketch=sketch.name):
                before = self._native(sketch)
                set_active_sketch(bpy.context, sketch)
                path = self.directory / (sketch.name + ".ifc")
                self.assertEqual(
                    bpy.ops.export_scene.cad_sketcher_ifc(filepath=str(path)),
                    {"FINISHED"},
                )
                document = self._reopen(path)
                profiles = document.by_type("IfcArbitraryClosedProfileDef")
                self.assertEqual(len(profiles), 1)
                profile = profiles[0]
                self.assertEqual(profile.ProfileName, sketch.name)
                self.assertEqual(
                    len(getattr(profile, "InnerCurves", ())), HOLES[sketch.name]
                )
                for hole in getattr(profile, "InnerCurves", ()):
                    self.assertTrue(hole.is_a("IfcCircle"))
                if sketch.name == "Pipe Sketch":
                    self.assertAlmostEqual(profile.OuterCurve.Radius, 27.5 * self.scale)
                    self.assertAlmostEqual(
                        profile.InnerCurves[0].Radius, 15 * self.scale
                    )
                self._receive_geometry(document, before)
                self.assertEqual(self._native(sketch), before)
                negative_trims += sum(
                    not curve.SenseAgreement
                    for curve in document.by_type("IfcTrimmedCurve")
                )
                combined.extend(sketch_profiles(sketch, unit_scale=self.scale))
        self.assertGreater(negative_trims, 0)
        path = self.directory / "part-library.ifc"
        write_sketch_profiles(path, combined, unit_scale=self.scale)
        document = self._reopen(path)
        self.assertEqual(
            {
                p.ProfileName: len(getattr(p, "InnerCurves", ()))
                for p in document.by_type("IfcArbitraryClosedProfileDef")
            },
            HOLES,
        )
        self.assertEqual(len(document.by_type("IfcArbitraryClosedProfileDef")), 6)

        # A duplicate authored diameter is consistent but redundant. Let the
        # actual solver classify it; a successful native solve remains exportable.
        pipe = next(s for s in self.sketches if s.name == "Pipe Sketch")
        circle = next(
            curve_ref(pipe, cid)
            for cid in read_uuid_list(pipe.data, "curve_id")
            if cid and curve_ref(pipe, cid).is_circle()
        )
        count = len(pipe.constraints.diameter)
        set_active_sketch(bpy.context, pipe)
        try:
            diameter = pipe.constraints.add_diameter(
                init=True, curve_id_1=circle.curve_id
            )
            duplicate = pipe.constraints.add_diameter(curve_id_1=circle.curve_id)
            duplicate.value = diameter.value
            self.assertEqual(len(pipe.constraints.diameter), count + 2)
            self.assertTrue(pipe.solve(bpy.context))
            self.assertEqual(pipe.solver_state, "REDUNDANT_OK")
            self.assertTrue(pipe.geometry_solved)
            path = self.directory / "redundant-pipe.ifc"
            self.assertEqual(
                bpy.ops.export_scene.cad_sketcher_ifc(filepath=str(path)), {"FINISHED"}
            )
            self._receive_geometry(self._reopen(path), self._native(pipe))
        finally:
            while len(pipe.constraints.diameter) > count:
                pipe.constraints.diameter.remove(len(pipe.constraints.diameter) - 1)
            self.assertTrue(pipe.solve(bpy.context))

    def test_unsupported_native_workplane_preserves_existing_destination(self) -> None:
        """A real scale edit is rejected before replacing a previously valid IFC."""
        sketch = next(s for s in self.sketches if s.name == "Back Plate A Sketch")
        set_active_sketch(bpy.context, sketch)
        prefs = get_prefs()
        prefs.enable_ifc_profile_export = False
        self.assertFalse(bpy.ops.export_scene.cad_sketcher_ifc.poll())
        prefs.enable_ifc_profile_export = True
        self.assertTrue(bpy.ops.export_scene.cad_sketcher_ifc.poll())
        path = self.directory / "existing.ifc"
        self.assertEqual(
            bpy.ops.export_scene.cad_sketcher_ifc(filepath=str(path)), {"FINISHED"}
        )
        before = path.read_bytes()
        plane = sketch.workplane_object or sketch.target_object
        original = plane.matrix_world.copy()
        try:
            plane.matrix_world = original @ Matrix.Diagonal((2.0, 1.0, 1.0, 1.0))
            with self.assertRaisesRegex(RuntimeError, "workplane scale or shear"):
                bpy.ops.export_scene.cad_sketcher_ifc(filepath=str(path))
        finally:
            plane.matrix_world = original
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [path])
        self._reopen(path)
