import logging
from typing import List

from bpy.props import StringProperty, BoolProperty
import bpy.types
from bpy.types import UILayout, Property, Context

from .. import functions
from ..solver import solve_system, Solver
from ..global_data import WpReq
from ..utilities import preferences
from ..declarations import Operators
from .constants import ENTITY_PROP_NAMES
from .base_entity import SlvsGenericEntity

logger = logging.getLogger(__name__)


class GenericConstraint:
    def _name_getter(self):
        return self.get("name", str(self))

    def _name_setter(self, new_name):
        self["name"] = new_name

    name: StringProperty(name="Name", get=_name_getter, set=_name_setter)
    failed: BoolProperty(name="Failed")
    visible: BoolProperty(name="Visible", default=True, update=functions.update_cb)
    signature = ()
    props = ()

    def needs_wp(args):
        return WpReq.OPTIONAL

    def __str__(self):
        return self.label

    def get_workplane(self):
        # NOTE: this could also check through the constraints entity workplanes
        needs_wp = self.needs_wp()

        workplane = None
        if self.sketch_i != -1:
            workplane = self.sketch.wp

        if workplane and needs_wp != WpReq.FREE:
            return workplane.py_data
        elif needs_wp == WpReq.NOT_FREE:
            return None
        else:
            from py_slvs import slvs

            return slvs.SLVS_FREE_IN_3D

    def entities(self):
        props = []
        for prop_name in dir(self):
            if prop_name.endswith("_i") or not prop_name.startswith("entity"):
                continue
            props.append(getattr(self, prop_name))
        return props

    def dependencies(self) -> List[SlvsGenericEntity]:
        deps = self.entities()
        if hasattr(self, "sketch"):
            s = self.sketch
            if s:
                deps.append(s)
        return deps

    def update_system_cb(self, context):
        """Update scene and re-run the solver.
        NOTE: Should be a staticmethod if it wasn't a callback."""
        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)

    # TODO: avoid duplicating code
    def update_pointers(self, index_old, index_new):
        def _update(name):
            prop = getattr(self, name)
            if prop == index_old:
                logger.debug(
                    "Update reference {} of {} to {}: ".format(name, self, index_new)
                )
                setattr(self, name, index_new)

        if hasattr(self, "sketch_i"):
            _update("sketch_i")

        for prop_name in dir(self):
            if not prop_name.startswith("entity") or not prop_name.endswith("_i"):
                continue
            _update(prop_name)

    def is_visible(self, context):
        if hasattr(self, "sketch"):
            return self.sketch.is_visible(context) and self.visible
        return self.visible

    def is_active(self, active_sketch):
        if not hasattr(self, "sketch"):
            return not active_sketch

        show_inactive = not preferences.use_experimental(
            "hide_inactive_constraints", True
        )
        if show_inactive:  # and self.is_visible(context)
            return True

        return self.sketch == active_sketch

    def draw_plane(self):
        if self.sketch_i != -1:
            wp = self.sketch.wp
            return wp.p1.location, wp.normal
        # TODO: return drawing plane for constraints in 3d
        return None, None

    def copy(self, context, entities):
        # copy itself to another set of entities
        c = context.scene.sketcher.constraints.new_from_type(self.type)
        if hasattr(self, "sketch"):
            c.sketch = self.sketch
        if hasattr(self, "setting"):
            c.setting = self.setting
        if hasattr(self, "value"):
            c.value = self.value

        for prop, e in zip(ENTITY_PROP_NAMES, entities):
            setattr(c, prop, e)

        return c

    def draw_props(self, layout: UILayout):
        is_experimental = preferences.is_experimental()

        layout.prop(self, "name", text="")

        if self.failed:
            layout.label(text="Failed", icon="ERROR")

        # Info block
        layout.separator()
        if is_experimental:
            sub = layout.column()
            sub.scale_y = 0.8
            sub.label(text="Dependencies:")
            for e in self.dependencies():
                sub.label(text=str(e))

        # General props
        layout.separator()
        layout.prop(self, "visible")

        # Specific props
        layout.separator()
        sub = layout.column()

        # Delete
        layout.separator()
        props = layout.operator(Operators.DeleteConstraint, icon="X")
        props.type = self.type
        props.index = self.index()

        return sub

    def index(self):
        """Return elements index inside its collection"""
        # HACK: Elements of collectionproperties currently don't expose an index
        # method, path_from_id writes the index however, use this hack instead
        # of looping over elements
        return int(self.path_from_id().split("[")[1].split("]")[0])

    def placements(self):
        """Return the entities where the constraint should be displayed"""
        return []

    def create_slvs_data(self, solvesys: Solver, **kwargs):
        raise NotImplementedError()

    def py_data(self, solvesys: Solver, **kwargs):
        return self.create_slvs_data(solvesys, **kwargs)


class DimensionalConstraint(GenericConstraint):

    value: Property
    setting: BoolProperty

    def _set_value(self, val: float):
        # NOTE: function signature _set_value(self, val: float, force=False)
        #       will fail when bpy tries to register the value property.
        #       See `_set_value_force()`
        if not self.is_reference:
            self._set_value_force(val)
    
    def _set_value_force(self, val: float):
        self["value"] = val

    def _get_value(self):
        if self.is_reference:
            val, _ = self.init_props()
            return self.to_displayed_value(val)
        if not self.get("value"):
            self.assign_init_props()
        return self["value"]

    def assign_init_props(self, context: Context = None):
        # self.value, self.setting = self.init_props()
        _value, _ = self.init_props()
        self._set_value_force(_value)

    def on_reference_checked(self, context: Context = None):
        self.assign_init_props()
        # Refresh the gizmos as we are changing the colors.
        functions.refresh(context)

    is_reference: BoolProperty(
        name="Only measure",
        default=False,
        update=on_reference_checked,
    )

    def init_props(self):
        raise NotImplementedError()

    def to_displayed_value(self, value):
        return value

    def py_data(self, solvesys: Solver, **kwargs):
        if self.is_reference:
            return []
        return self.create_slvs_data(solvesys, **kwargs)

    def draw_props(self, layout: UILayout):
        sub = GenericConstraint.draw_props(self, layout)
        sub.prop(self, "is_reference")
        if hasattr(self, "value"):
            col = sub.column()
            # Could not find a way to have the property "readonly",
            # so we disable user input instead
            col.prop(self, "value")
            col.enabled = not self.is_reference
        if hasattr(self, "setting"):
            row = sub.row()
            row.prop(self, "setting")
        return sub
