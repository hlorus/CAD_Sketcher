"""Sketch accessor — wraps a Blender Curves Object as a sketch.

A sketch IS a Curves object with custom properties. This module provides
the Sketch wrapper class and helpers for discovery and activation.
"""

import bpy

from .. import global_data

# Custom property keys on the Curves object
_TAG = "is_cad_sketch"
_SOLVER_STATE = "solver_state"
_DOF = "dof"
_IS_3D = "is_3d_sketch"

# Object name of a sketch datablock's owning object, stamped on the Curves *data*
# so a linked duplicate (which shares the data) can be told from its source (see
# utilities.consumable).
_OWNER = "slvs:sketch_owner"
# Marks a sketch we took out of the viewport ourselves, so the overlay can keep
# drawing it while Blender does not draw its curves.
_MANAGED_HIDE = "slvs:managed_hide"


class Sketch:
    """Lightweight accessor wrapping a Blender Curves Object as a sketch."""

    __slots__ = ("_obj",)

    def __init__(self, obj):
        self._obj = obj

    # -- Object access --

    @property
    def target_object(self):
        return self._obj

    @property
    def workplane_object(self):
        """The Object providing this sketch's plane, or None if it is its own.

        Stored as an explicit pointer rather than read from ``parent``: a sketch
        that owns its transform (nothing above it in the hierarchy places it)
        still has a plane, and its plane is its own frame. Old files predate the
        pointer, so fall back to the parent, which is what placed them.
        """
        obj = self._obj
        wp = getattr(obj, "slvs_workplane", None)
        return wp if wp is not None else obj.parent

    @workplane_object.setter
    def workplane_object(self, value):
        self._obj.slvs_workplane = value

    @property
    def plane_matrix(self):
        """The frame this sketch's local coordinates are expressed in.

        The single answer to "where is this sketch": its workplane's frame, or
        its own when it has no workplane object. Every consumer that unprojects
        a click, seeds the solver, or places a gizmo must go through here, so
        that they cannot disagree about which matrix resolves a stored point.
        """
        wp = self.workplane_object
        if wp is not None:
            return wp.matrix_world
        return self._obj.matrix_world

    @property
    def world_matrix(self):
        """The sketch's world frame for placing and reading geometry.

        The same frame the solver works in: drawing, picking and solving must not
        disagree about where a stored coordinate ends up. A free-3D sketch is
        anchored by an origin Empty and a 2D one by its workplane; both are the
        sketch's plane object, and reading it (rather than the Curves object's own
        derived matrix) also avoids the child lagging its frame between depsgraph
        updates while that frame is dragged.
        """
        return self.plane_matrix

    @property
    def is_3d(self):
        """Whether this sketch is free in 3D instead of workplane-bound."""
        return bool(self._obj.get(_IS_3D, False))

    @property
    def data(self):
        return self._obj.data

    @property
    def constraints(self):
        return self._obj.data.sketch_constraints

    @property
    def topology(self):
        from ..utilities.topology import SketchTopology

        return SketchTopology(self)

    @property
    def name(self):
        return self._obj.name

    @name.setter
    def name(self, value):
        self._obj.name = value

    # -- Custom properties --

    @property
    def solver_state(self):
        return self._obj.get(_SOLVER_STATE, "OKAY")

    @solver_state.setter
    def solver_state(self, value):
        self._obj[_SOLVER_STATE] = value

    @property
    def geometry_solved(self):
        return self._obj.get("geometry_solved", True)

    @geometry_solved.setter
    def geometry_solved(self, value):
        self._obj["geometry_solved"] = value

    @property
    def dof(self):
        return self._obj.get(_DOF, 0)

    @dof.setter
    def dof(self, value):
        self._obj[_DOF] = value

    # -- Visibility --

    def is_visible(self, context):
        active = get_active_sketch(context)
        if active and active._obj == self._obj:
            return True
        if self._obj.get(_MANAGED_HIDE, False):
            # We hid the curves so they do not double up on the body's mesh; the
            # sketch is still ours to draw, unless the user hid it themselves.
            return not self._obj.hide_get()
        # visible_get() covers the eye-icon hide and collection visibility, not
        # just hide_viewport (the monitor icon) -- so an eye-hidden sketch isn't
        # drawn or pickable, matching the workplane overlay behaviour.
        return self._obj.visible_get()

    # -- Solver --

    def get_solver_state(self):
        from ..utilities.bpy import bpyEnum

        return bpyEnum(global_data.solver_state_items, identifier=self.solver_state)

    def solve(self, context):
        from ..curve_solver import solve_system

        return solve_system(context, sketch=self)

    # -- Cleanup --

    def remove_objects(self):
        if not self._obj:
            return

        obj = self._obj
        parent = obj.parent
        remove_origin = bool(
            self.is_3d and parent and parent.get("is_3d_sketch_origin", False)
        )

        from ..utilities.body import remove_body

        remove_body(obj)
        bpy.data.objects.remove(obj)
        if remove_origin and parent.name in bpy.data.objects:
            bpy.data.objects.remove(parent)

    # -- Identity --

    def __eq__(self, other):
        if isinstance(other, Sketch):
            return self._obj == other._obj
        return NotImplemented

    def __hash__(self):
        return hash(id(self._obj))

    def __repr__(self):
        return f"Sketch({self._obj.name!r})"

    def __bool__(self):
        try:
            return self._obj is not None and self._obj.name is not None
        except ReferenceError:
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def stamp_sketch_props(obj):
    """Stamp custom properties on a Curves object to mark it as a sketch."""
    obj[_TAG] = True
    if _SOLVER_STATE not in obj:
        obj[_SOLVER_STATE] = "OKAY"
    if _DOF not in obj:
        obj[_DOF] = 0
    # Record the owning object on the *data*, so a later linked duplicate (which
    # shares this data) can be recognised as a copy of ``obj``. Only claim it if
    # unset, a copy stamped over shared data must not steal ownership.
    if obj.data is not None and _OWNER not in obj.data:
        obj.data[_OWNER] = obj.name


def is_sketch_object(obj):
    """Check if a Blender object is a CAD Sketcher sketch."""
    return obj and obj.type == "CURVES" and obj.get(_TAG, False)


def get_sketches(context_or_scene):
    """Yield Sketch accessors for all sketches in the scene."""
    scene = (
        context_or_scene
        if hasattr(context_or_scene, "objects")
        else context_or_scene.scene
    )
    for obj in scene.objects:
        if is_sketch_object(obj):
            yield Sketch(obj)


def get_active_constraints(context):
    """Get constraints for the active sketch, or None."""
    sketch = get_active_sketch(context)
    if sketch:
        return sketch.constraints
    return None


def get_active_sketch(context):
    """Get the active sketch, or None."""
    obj = context.scene.sketcher.active_sketch_object
    if obj and is_sketch_object(obj):
        return Sketch(obj)
    return None


def poll_active_2d_sketch(context) -> bool:
    """Poll for 2D-only drawing operators: an active sketch that isn't free-3D.

    Shared so every 2D drawing op (point/line/circle/arc/rectangle) rejects a
    stale hotkey/operator path that would otherwise write planar XY geometry into
    a free-3D sketch.
    """
    obj = context.scene.sketcher.active_sketch_object
    if obj is None:
        return False
    return not Sketch(obj).is_3d


def hide_sketch_curves(sketch_obj) -> None:
    """Take a sketch's curves out of the viewport, leaving it to the overlay.

    The geometry the user sees is the body's mesh, drawn in the same place: left
    visible the curves sit on top of it as a second outline. ``hide_viewport``
    is what instances of a part honour (the eye is view-layer state only), and
    the body's modifier reads the sketch anyway, so it stays evaluated.
    """
    sketch_obj[_MANAGED_HIDE] = True
    sketch_obj.hide_viewport = True


def set_active_sketch(context, sketch_or_obj):
    """Set the active sketch. Pass Sketch, Object, or None."""
    if sketch_or_obj is None:
        context.scene.sketcher.active_sketch_object = None
    elif isinstance(sketch_or_obj, Sketch):
        context.scene.sketcher.active_sketch_object = sketch_or_obj._obj
    else:
        context.scene.sketcher.active_sketch_object = sketch_or_obj
