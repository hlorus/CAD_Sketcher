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
        return self._obj.parent

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
        return not self._obj.hide_viewport

    # -- Solver --

    def get_solver_state(self):
        from ..utilities.bpy import bpyEnum
        return bpyEnum(global_data.solver_state_items, identifier=self.solver_state)

    def solve(self, context):
        from ..curve_solver import solve_system
        return solve_system(context, sketch=self)

    # -- Cleanup --

    def remove_objects(self):
        if self._obj:
            bpy.data.objects.remove(self._obj)

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


def is_sketch_object(obj):
    """Check if a Blender object is a CAD Sketcher sketch."""
    return obj and obj.type == 'CURVES' and obj.get(_TAG, False)


def get_sketches(context_or_scene):
    """Yield Sketch accessors for all sketches in the scene."""
    scene = context_or_scene if hasattr(context_or_scene, 'objects') else context_or_scene.scene
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


def set_active_sketch(context, sketch_or_obj):
    """Set the active sketch. Pass Sketch, Object, or None."""
    if sketch_or_obj is None:
        context.scene.sketcher.active_sketch_object = None
    elif isinstance(sketch_or_obj, Sketch):
        context.scene.sketcher.active_sketch_object = sketch_or_obj._obj
    else:
        context.scene.sketcher.active_sketch_object = sketch_or_obj
