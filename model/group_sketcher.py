import logging
from typing import Generator, Union

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatVectorProperty,
    IntProperty,
    IntVectorProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Context, PropertyGroup
from bpy.utils import register_class, unregister_class

from .. import global_data
from ..curve_solver import solve_system
from ..drawing import selection
from ..utilities.view import update_cb
from .base_entity import SlvsGenericEntity
from .group_constraints import SlvsConstraints
from .group_entities import SlvsEntities

logger = logging.getLogger(__name__)

# Prefix for all constraint driver target custom properties on the scene.
_EP_PREFIX = "slvs:c:"


# Set while loading current values into the coordinate editor so seeding the
# fields does not fire the write-through update callback.
_SEEDING_COORDS = False


def _solver_wp_matrix(sketch):
    """The workplane matrix the solver uses, for placing a drag target."""
    from mathutils import Matrix

    wp_obj = sketch.workplane_object
    if not wp_obj and sketch.target_object:
        wp_obj = sketch.target_object.parent
    return wp_obj.matrix_world if wp_obj else Matrix.Identity(4)


def _update_coord_editor(self, context: Context) -> None:
    """Write the edited coordinate straight through to the point and re-solve.

    Mirrors the pre-0.30 inline ``co`` field: a real property with an update
    callback commits reliably from the context-menu popup (unlike an operator
    dialog, whose per-field commits proved unreliable there).
    """
    if _SEEDING_COORDS:
        return

    from mathutils import Vector

    from ..curve_solver import CurveSolver, solve_system
    from ..model.curve_ref import curve_ref
    from ..model.native_3d import rebuild_3d_lines
    from ..model.sketch_ref import get_active_sketch
    from ..utilities.curve_data import refresh_curve_geometry

    sketch = get_active_sketch(context)
    if not sketch or not self.curve_id:
        return
    ref = curve_ref(sketch, self.curve_id)
    if not ref.valid or not ref.is_point():
        return

    sketch.geometry_solved = False
    if sketch.is_3d:
        # The 3D solver has no drag support; write the position and solve.
        if not ref._resolve():
            return
        curve_data = sketch.target_object.data
        pt_idx = ref._curve_slice.points[0].index
        curve_data.points[pt_idx].position = tuple(self.co_3d)
        rebuild_3d_lines(sketch)
        curve_data.update_tag()
        solve_system(context, sketch=sketch)
    else:
        ref.co = (self.co_2d[0], self.co_2d[1])
        # Pin the point at the typed position with a drag, so a still-movable
        # (under-constrained) point stays where the user placed it instead of
        # being snapped back by the re-solve. A fully-constrained point can't
        # move: the solver drops the drag and keeps the constrained solution.
        wp_mat = _solver_wp_matrix(sketch)
        target = wp_mat @ Vector((self.co_2d[0], self.co_2d[1], 0.0))
        solver = CurveSolver(context, sketch)
        solver.tweak(self.curve_id, target)
        solver.solve()

    refresh_curve_geometry(sketch)
    if context.area:
        context.area.tag_redraw()


def _update_entity_name(self, context: Context) -> None:
    """Rename the edited entity through its curve ``name`` attribute."""
    if _SEEDING_COORDS:
        return

    from ..model.curve_ref import curve_ref
    from ..model.sketch_ref import get_active_sketch

    sketch = get_active_sketch(context)
    if not sketch or not self.curve_id:
        return
    ref = curve_ref(sketch, self.curve_id)
    if not ref.valid:
        return
    ref.name = self.name
    if context.area:
        context.area.tag_redraw()


class SlvsCoordEditor(PropertyGroup):
    """Editable settings for the entity currently shown in the context menu.

    ``name`` applies to any entity; ``co_2d`` is drawn for a point on a planar
    sketch (X/Y only) and ``co_3d`` for a point on a free-3D sketch. Each writes
    straight through to the curve via its update callback.
    """

    curve_id: StringProperty(options={"SKIP_SAVE"})
    name: StringProperty(name="Name", update=_update_entity_name)
    co_2d: FloatVectorProperty(
        name="Coordinates", subtype="XYZ", size=2, update=_update_coord_editor
    )
    co_3d: FloatVectorProperty(
        name="Coordinates", subtype="XYZ", size=3, update=_update_coord_editor
    )


def seed_entity_editor(context: Context, ref) -> None:
    """Aim the entity editor at ``ref`` and load its current settings.

    Loads the name for any entity and the position for points; guarded so
    seeding does not fire the write-through callbacks.
    """
    global _SEEDING_COORDS

    editor = context.scene.sketcher.coord_editor
    _SEEDING_COORDS = True
    try:
        editor.curve_id = ref.curve_id
        editor.name = ref.name
        if ref.is_point():
            pos = ref._first_point_3d()
            editor.co_2d = (pos.x, pos.y)
            editor.co_3d = (pos.x, pos.y, pos.z)
    finally:
        _SEEDING_COORDS = False


class ProjectedSourceSlot(PropertyGroup):
    """Object pointer used by native projected-curve bindings.

    Curve-domain integer attributes store the index into this compact table so
    all plain binding data can live on the Curves datablock while the one value
    Blender attributes cannot represent (an ID pointer) remains a real RNA
    pointer rather than a fragile object-name string.
    """

    source: PointerProperty(type=bpy.types.Object, name="Projected Source")


class SketcherProps(PropertyGroup):
    """The base structure for CAD Sketcher"""

    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    coord_editor: PointerProperty(type=SlvsCoordEditor)
    show_origin: BoolProperty(name="Show Origin Workplanes", default=True)

    # Origin workplane empties
    wp_xy: PointerProperty(type=bpy.types.Object, name="XY Workplane")
    wp_xz: PointerProperty(type=bpy.types.Object, name="XZ Workplane")
    wp_yz: PointerProperty(type=bpy.types.Object, name="YZ Workplane")

    use_construction: BoolProperty(
        name="Construction Mode",
        description="Draw all subsequent entities in construction mode",
        default=False,
        options={"SKIP_SAVE"},
        update=update_cb,
    )
    auto_axis_constraints: BoolProperty(
        name="Auto Constraints",
        description="Automatically add inferred constraints (for example auto axis alignment and auto coincident)",
        default=True,
        options={"SKIP_SAVE"},
        update=update_cb,
    )
    use_snap_project: BoolProperty(
        name="Live Project Snaps",
        description=(
            "When snapping a point onto external mesh geometry, project the "
            "snapped element into the sketch as a live reference and link the "
            "point to it, instead of placing a dead static point"
        ),
        default=True,
        options={"SKIP_SAVE"},
        update=update_cb,
    )
    version: IntVectorProperty(
        name="Extension Version",
        description="CAD Sketcher extension version this scene was saved with",
    )

    # Active sketch — the Curves object being edited
    active_sketch_object: PointerProperty(
        type=bpy.types.Object,
        name="Active Sketch Object",
    )

    # This is needed for the sketches ui list
    ui_active_sketch: IntProperty()

    @property
    def all(self) -> Generator[Union[SlvsGenericEntity, SlvsConstraints], None, None]:
        """Iterate over entities and constraints of every type"""
        for entity in self.entities.all:
            yield entity
        for constraint in self.constraints.all:
            yield constraint

    def solve(self, context: Context):
        return solve_system(context)

    def create_constraint_value_endpoint(self, constraint) -> str | None:
        uid = getattr(constraint, "constraint_uid", "")
        if not uid:
            return None
        scene = self.id_data
        key = f"{_EP_PREFIX}{uid}"
        if key not in scene:
            if hasattr(constraint, "value_store") and constraint.is_property_set(
                "value_store"
            ):
                init_value = float(constraint.value_store)
            elif hasattr(constraint, "value") and constraint.is_property_set("value"):
                init_value = float(constraint.value)
            else:
                init_value = 0.0

            scene[key] = init_value
            try:
                rna_prop = type(constraint).bl_rna.properties.get("value_store")
                subtype = rna_prop.subtype if rna_prop else "NONE"
                scene.id_properties_ui(key).update(
                    subtype=subtype, min=0.0, soft_min=0.0
                )
            except Exception:
                pass
        return key

    def get_constraint_value_endpoint(self, constraint) -> str | None:
        uid = getattr(constraint, "constraint_uid", "")
        if not uid:
            return None
        key = f"{_EP_PREFIX}{uid}"
        scene = self.id_data
        return key if key in scene else None

    def remove_constraint_value_endpoint(self, constraint_uid: str):
        """Delete the scene custom property for a constraint that is being removed."""
        if not constraint_uid:
            return
        scene = self.id_data
        key = f"{_EP_PREFIX}{constraint_uid}"
        if key in scene:
            del scene[key]

    def purge_stale_data(self):
        selection.hover = ""
        selection.selected.clear()
        global_data.batches.clear()
        for e in self.entities.all:
            e.dirty = True


def register():
    register_class(SlvsCoordEditor)
    register_class(ProjectedSourceSlot)
    register_class(SketcherProps)
    bpy.types.Object.slvs_project_sources = CollectionProperty(type=ProjectedSourceSlot)
    bpy.types.Scene.sketcher = PointerProperty(type=SketcherProps)


def unregister():
    del bpy.types.Object.slvs_project_sources
    del bpy.types.Scene.sketcher
    unregister_class(SketcherProps)
    unregister_class(ProjectedSourceSlot)
    unregister_class(SlvsCoordEditor)
