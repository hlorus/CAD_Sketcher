"""
Operators
"""
import logging
import math
from collections import deque, namedtuple
from typing import Deque, Generator

import bpy
from bl_operators.presets import AddPresetBase
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Context, Event, Operator, Scene
from mathutils import Vector
from mathutils.geometry import intersect_line_plane


from . import class_defines, functions, global_data

from .declarations import Operators, VisibilityTypes
from .class_defines import (
    SlvsConstraints,
    SlvsGenericEntity,
    SlvsSketch,
)
from .solver import solve_system
from .functions import show_ui_message_popup
from .operators.utilities import activate_sketch
from .utilities.highlighting import HighlightElement
from .stateful_operator.integration import StatefulOperator
from .stateful_operator.state import state_from_args
from .operators.base_stateful import GenericEntityOp
from .operators.utilities import deselect_all

logger = logging.getLogger(__name__)


def add_point(context, pos, name=""):
    data = bpy.data
    ob = data.objects.new(name, None)
    ob.location = pos
    context.collection.objects.link(ob)
    return ob



def get_flat_deps(entity):
    """Return flattened list of entities given entity depends on"""
    list = []

    def walker(entity, is_root=False):
        if entity in list:
            return
        if not is_root:
            list.append(entity)
        if not hasattr(entity, "dependencies"):
            return
        for e in entity.dependencies():
            if e in list:
                continue
            walker(e)

    walker(entity, is_root=True)
    return list


def get_scene_constraints(scene: Scene):
    return scene.sketcher.constraints.all


def get_scene_entities(scene: Scene):
    return scene.sketcher.entities.all


def get_entity_deps(
    entity: SlvsGenericEntity, context: Context
) -> Generator[SlvsGenericEntity, None, None]:
    for scene_entity in get_scene_entities(context.scene):
        deps = set(get_flat_deps(scene_entity))
        if entity in deps:
            yield scene_entity


def is_entity_referenced(entity: SlvsGenericEntity, context: Context) -> bool:
    """Check if entity is a dependency of another entity"""
    deps = get_entity_deps(entity, context)
    try:
        next(deps)
    except StopIteration:
        return False
    return True


def get_sketch_deps_indicies(sketch: SlvsSketch, context: Context):
    deps = deque()
    for entity in get_scene_entities(context.scene):
        if not hasattr(entity, "sketch_i"):
            continue
        if sketch.slvs_index != entity.sketch.slvs_index:
            continue
        deps.append(entity.slvs_index)
    return deps


def get_constraint_local_indices(
    entity: SlvsGenericEntity, context: Context
) -> Deque[int]:
    constraints = context.scene.sketcher.constraints
    ret_list = deque()

    for data_coll in constraints.get_lists():
        indices = deque()
        for c in data_coll:
            if entity in c.dependencies():
                indices.append(constraints.get_index(c))
        ret_list.append((data_coll, indices))
    return ret_list


class View3D_OT_slvs_delete_entity(Operator, HighlightElement):
    """Delete Entity by index or based on the selection if index isn't provided"""

    bl_idname = Operators.DeleteEntity
    bl_label = "Delete Solvespace Entity"
    bl_options = {"UNDO"}
    bl_description = (
        "Delete Entity by index or based on the selection if index isn't provided"
    )

    index: IntProperty(default=-1)

    @staticmethod
    def main(context: Context, index: int, operator: Operator):
        entities = context.scene.sketcher.entities
        entity = entities.get(index)

        if not entity:
            return {"CANCELLED"}

        if isinstance(entity, class_defines.SlvsSketch):
            if context.scene.sketcher.active_sketch_i != -1:
                activate_sketch(context, -1, operator)
            entity.remove_objects()

            deps = get_sketch_deps_indicies(entity, context)

            for i in reversed(deps):
                operator.delete(entities.get(i), context)

        elif is_entity_referenced(entity, context):
            deps = list(get_entity_deps(entity, context))

            message = f"Unable to delete {entity.name}, other entities depend on it:\n"+ "\n".join(
                [f" - {d}" for d in deps]
            )
            show_ui_message_popup(message=message, icon="ERROR")

            operator.report(
                {"WARNING"},
                "Cannot delete {}, other entities depend on it.".format(
                    entity.name
                ),
            )
            return {"CANCELLED"}

        operator.delete(entity, context)

    @staticmethod
    def delete(entity, context: Context):
        entity.selected = False

        # Delete constraints that depend on entity
        constraints = context.scene.sketcher.constraints

        for data_coll, indices in reversed(get_constraint_local_indices(entity, context)):
            if not indices:
                continue
            for i in indices:
                logger.debug("Delete: {}".format(data_coll[i]))
                data_coll.remove(i)

        logger.debug("Delete: {}".format(entity))
        entities = context.scene.sketcher.entities
        entities.remove(entity.slvs_index)

    def execute(self, context: Context):
        index = self.index
        selected = context.scene.sketcher.entities.selected_entities

        if index != -1:
            # Entity is specified via property
            self.main(context, index, self)
        elif len(selected) == 1:
            # Treat single selection same as specified entity
            self.main(context, selected[0].slvs_index, self)
        else:
            # Batch deletion
            indices = []
            for e in selected:
                indices.append(e.slvs_index)

            indices.sort(reverse=True)
            for i in indices:
                e = context.scene.sketcher.entities.get(i)

                # NOTE: this might be slow when a lot of entities are selected, improve!
                if is_entity_referenced(e, context):
                    continue
                self.delete(e, context)

        functions.refresh(context)
        return {"FINISHED"}


state_docstr = "Pick entity to constrain."


class GenericConstraintOp(GenericEntityOp):
    initialized: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    _entity_prop_names = ("entity1", "entity2", "entity3", "entity4")

    def _available_entities(self):
        # Gets entities that are already set
        cls = SlvsConstraints.cls_from_type(self.type)
        entities = [None] * len(cls.signature)
        for i, name in enumerate(self._entity_prop_names):
            if hasattr(self, name):
                e = getattr(self, name)
                if not e:
                    continue
                entities[i] = e
        return entities

    @classmethod
    def states(cls, operator=None):
        states = []

        cls_constraint = SlvsConstraints.cls_from_type(cls.type)

        for i, _ in enumerate(cls_constraint.signature):
            name_index = i + 1
            if hasattr(cls_constraint, "get_types") and operator:
                types = cls_constraint.get_types(i, operator._available_entities())
            else:
                types = cls_constraint.signature[i]

            if not types:
                break

            states.append(
                state_from_args(
                    "Entity " + str(name_index),
                    description=state_docstr,
                    pointer="entity" + str(name_index),
                    property=None,
                    types=types,
                )
            )
        return states

    def initialize_constraint(self):
        c = self.target
        if not self.initialized and hasattr(c, "init_props"):
            kwargs = {}
            if hasattr(self, "value") and self.properties.is_property_set("value"):
                kwargs["value"] = self.value
            if hasattr(self, "setting") and self.properties.is_property_set("setting"):
                kwargs["setting"] = self.setting

            value, setting = c.init_props(**kwargs)
            if value is not None:
                self.value = value
            if setting is not None:
                self.setting = setting
        self.initialized = True

    def fill_entities(self):
        c = self.target
        args = []
        # fill in entities!
        for prop in self._entity_prop_names:
            if hasattr(c, prop):
                value = getattr(self, prop)
                setattr(c, prop, value)
                args.append(value)
        return args

    def main(self, context):
        c = self.target = context.scene.sketcher.constraints.new_from_type(self.type)
        self.sketch = context.scene.sketcher.active_sketch
        entities = self.fill_entities()
        c.sketch = self.sketch

        self.initialize_constraint()

        if hasattr(c, "value"):
            c["value"] = self.value
        if hasattr(c, "setting"):
            c["setting"] = self.setting

        deselect_all(context)
        solve_system(context, sketch=self.sketch)
        functions.refresh(context)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

    def draw(self, context):
        layout = self.layout

        c = self.target
        if not c:
            return

        if hasattr(c, "value"):
            layout.prop(self, "value")
        if hasattr(c, "setting"):
            layout.prop(self, "setting")

        if hasattr(self, "draw_settings"):
            self.draw_settings(context)


# Dimensional constraints
class VIEW3D_OT_slvs_add_distance(Operator, GenericConstraintOp):
    """Add a distance constraint"""

    bl_idname = Operators.AddDistance
    bl_label = "Distance"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Distance",
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=5,
        options={"SKIP_SAVE"},
    )
    align: EnumProperty(name="Alignment", items=class_defines.align_items)
    type = "DISTANCE"

    def fini(self, context, succeede):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.align = self.align
            self.target.draw_offset = 0.05 * context.region_data.view_distance

    def draw_settings(self, context):
        if not hasattr(self, "target"):
            return

        layout = self.layout

        row = layout.row()
        row.active = self.target.use_align()
        row.prop(self, "align")


def invert_angle_getter(self):
    return self.get("setting", self.bl_rna.properties["setting"].default)


def invert_angle_setter(self, setting):
    self["value"] = math.pi - self.value
    self["setting"] = setting


class VIEW3D_OT_slvs_add_angle(Operator, GenericConstraintOp):
    """Add an angle constraint"""

    bl_idname = Operators.AddAngle
    bl_label = "Angle"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        unit="ROTATION",
        options={"SKIP_SAVE"},
        precision=5,
    )
    setting: BoolProperty(name="Measure supplementary angle", default = False, get=invert_angle_getter, set=invert_angle_setter)
    type = "ANGLE"

    def fini(self, context, succeede):
        super().fini(context, succeede)
        if hasattr(self, "target"):
            self.target.draw_offset = 0.1 * context.region_data.view_distance


class VIEW3D_OT_slvs_add_diameter(Operator, GenericConstraintOp):
    """Add a diameter constraint"""

    bl_idname = Operators.AddDiameter
    bl_label = "Diameter"
    bl_options = {"UNDO", "REGISTER"}

    # Either Radius or Diameter
    value: FloatProperty(
        name="Size",
        subtype="DISTANCE",
        unit="LENGTH",
        options={"SKIP_SAVE"},
        precision=5,
    )

    setting: BoolProperty(name="Use Radius")
    type = "DIAMETER"


# Geomteric constraints
class VIEW3D_OT_slvs_add_coincident(Operator, GenericConstraintOp):
    """Add a coincident constraint"""

    bl_idname = Operators.AddCoincident
    bl_label = "Coincident"
    bl_options = {"UNDO", "REGISTER"}

    type = "COINCIDENT"

    def main(self, context: Context):
        p1, p2 = self.entity1, self.entity2
        if all([e.is_point() for e in (p1, p2)]):
            # Implicitly merge points
            class_defines.update_pointers(context.scene, p1.slvs_index, p2.slvs_index)
            context.scene.sketcher.entities.remove(p1.slvs_index)
            solve_system(context, context.scene.sketcher.active_sketch)
            return True
        return super().main(context)


class VIEW3D_OT_slvs_add_equal(Operator, GenericConstraintOp):
    """Add an equal constraint"""

    bl_idname = Operators.AddEqual
    bl_label = "Equal"
    bl_options = {"UNDO", "REGISTER"}

    type = "EQUAL"


class VIEW3D_OT_slvs_add_vertical(Operator, GenericConstraintOp):
    """Add a vertical constraint"""

    bl_idname = Operators.AddVertical
    bl_label = "Vertical"
    bl_options = {"UNDO", "REGISTER"}

    type = "VERTICAL"


class VIEW3D_OT_slvs_add_horizontal(Operator, GenericConstraintOp):
    """Add a horizontal constraint"""

    bl_idname = Operators.AddHorizontal
    bl_label = "Horizontal"
    bl_options = {"UNDO", "REGISTER"}

    type = "HORIZONTAL"


class VIEW3D_OT_slvs_add_parallel(Operator, GenericConstraintOp):
    """Add a parallel constraint"""

    bl_idname = Operators.AddParallel
    bl_label = "Parallel"
    bl_options = {"UNDO", "REGISTER"}

    type = "PARALLEL"


class VIEW3D_OT_slvs_add_perpendicular(Operator, GenericConstraintOp):
    """Add a perpendicular constraint"""

    bl_idname = Operators.AddPerpendicular
    bl_label = "Perpendicular"
    bl_options = {"UNDO", "REGISTER"}

    type = "PERPENDICULAR"


class VIEW3D_OT_slvs_add_tangent(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a tagent constraint"""

    bl_idname = Operators.AddTangent
    bl_label = "Tangent"
    bl_options = {"UNDO", "REGISTER"}

    type = "TANGENT"


class VIEW3D_OT_slvs_add_midpoint(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a midpoint constraint"""

    bl_idname = Operators.AddMidPoint
    bl_label = "Midpoint"
    bl_options = {"UNDO", "REGISTER"}

    type = "MIDPOINT"


class VIEW3D_OT_slvs_add_ratio(Operator, GenericConstraintOp, GenericEntityOp):
    """Add a ratio constraint"""

    value: FloatProperty(
        name="Ratio", subtype="UNSIGNED", options={"SKIP_SAVE"}, min=0.0, precision=5,
    )
    bl_idname = Operators.AddRatio
    bl_label = "Ratio"
    bl_options = {"UNDO", "REGISTER"}

    type = "RATIO"


class View3D_OT_slvs_set_all_constraints_visibility(Operator, HighlightElement):
    """Set all constraints' visibility
    """
    _visibility_items = [
        (VisibilityTypes.Hide, "Hide all", "Hide all constraints"),
        (VisibilityTypes.Show, "Show all", "Show all constraints"),
    ]

    bl_idname = Operators.SetAllConstraintsVisibility
    bl_label = "Set all constraints' visibility"
    bl_options = {"UNDO"}
    bl_description = "Set all constraints' visibility"

    visibility: EnumProperty(
        name="Visibility",
        description="Visiblity",
        items=_visibility_items)

    @classmethod
    def poll(cls, context):
        return True

    @classmethod
    def description(cls, context, properties):
        for vi in cls._visibility_items:
            if vi[0] == properties.visibility:
                return vi[2]
        return None

    def execute(self, context):
        constraint_lists = context.scene.sketcher.constraints.get_lists()
        for constraint_list in constraint_lists:
            for constraint in constraint_list:
                if not hasattr(constraint, "visible"):
                    continue
                constraint.visible = self.visibility == "SHOW"
        return {"FINISHED"}


class View3D_OT_slvs_delete_constraint(Operator, HighlightElement):
    """Delete constraint by type and index
    """

    bl_idname = Operators.DeleteConstraint
    bl_label = "Delete Constraint"
    bl_options = {"UNDO"}
    bl_description = "Delete Constraint"

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    @classmethod
    def description(cls, context, properties):
        cls.handle_highlight_hover(context, properties)
        if properties.type:
            return "Delete: " + properties.type.capitalize()
        return ""

    def execute(self, context: Context):
        constraints = context.scene.sketcher.constraints

        # NOTE: It's not really necessary to first get the
        # constraint from it's index before deleting

        constr = constraints.get_from_type_index(self.type, self.index)
        logger.debug("Delete: {}".format(constr))

        constraints.remove(constr)

        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        functions.refresh(context)
        return {"FINISHED"}


class View3D_OT_slvs_tweak_constraint_value_pos(Operator):
    bl_idname = Operators.TweakConstraintValuePos
    bl_label = "Tweak Constraint"
    bl_options = {"UNDO"}
    bl_description = "Tweak constraint's value or display position"

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    def invoke(self, context: Context, event: Event):
        self.tweak = False
        self.init_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        delta = (
            self.init_mouse_pos - Vector((event.mouse_region_x, event.mouse_region_y))
        ).length
        if not self.tweak and delta > 6:
            self.tweak = True

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if not self.tweak:
                self.execute(context)
            return {"FINISHED"}

        if not self.tweak:
            return {"RUNNING_MODAL"}

        coords = event.mouse_region_x, event.mouse_region_y

        constraints = context.scene.sketcher.constraints
        constr = constraints.get_from_type_index(self.type, self.index)

        origin, end_point = functions.get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, *constr.draw_plane())

        mat = constr.matrix_basis()
        pos = mat.inverted() @ pos

        constr.update_draw_offset(pos, context.preferences.system.ui_scale)
        context.space_data.show_gizmo = True
        return {"RUNNING_MODAL"}

    def execute(self, context: Context):
        bpy.ops.view3d.slvs_context_menu(type=self.type, index=self.index)
        return {"FINISHED"}


class SKETCHER_OT_add_preset_theme(AddPresetBase, Operator):
    """Add an Theme Preset"""

    bl_idname = Operators.AddPresetTheme
    bl_label = "Add Theme Preset"
    preset_menu = "SKETCHER_MT_theme_presets"

    preset_defines = [
        'prefs = bpy.context.preferences.addons["CAD_Sketcher"].preferences',
        "theme = prefs.theme_settings",
        "entity = theme.entity",
        "constraint = theme.constraint",
    ]

    preset_values = [
        "entity.default",
        "entity.highlight",
        "entity.selected",
        "entity.selected_highlight",
        "entity.inactive",
        "entity.inactive_selected",
        "constraint.default",
        "constraint.highlight",
        "constraint.failed",
        "constraint.failed_highlight",
        "constraint.text",
    ]

    preset_subdir = "bgs/theme"




constraint_operators = (
    VIEW3D_OT_slvs_add_distance,
    VIEW3D_OT_slvs_add_diameter,
    VIEW3D_OT_slvs_add_angle,
    VIEW3D_OT_slvs_add_coincident,
    VIEW3D_OT_slvs_add_equal,
    VIEW3D_OT_slvs_add_vertical,
    VIEW3D_OT_slvs_add_horizontal,
    VIEW3D_OT_slvs_add_parallel,
    VIEW3D_OT_slvs_add_perpendicular,
    VIEW3D_OT_slvs_add_tangent,
    VIEW3D_OT_slvs_add_midpoint,
    VIEW3D_OT_slvs_add_ratio,
)

from .stateful_operator.invoke_op import View3D_OT_invoke_tool

classes = (
    View3D_OT_invoke_tool,
    View3D_OT_slvs_set_all_constraints_visibility,
    View3D_OT_slvs_delete_entity,
    *constraint_operators,
    View3D_OT_slvs_delete_constraint,
    View3D_OT_slvs_tweak_constraint_value_pos,
    SKETCHER_OT_add_preset_theme,
)


def register():
    for cls in classes:
        if issubclass(cls, StatefulOperator):
            cls.register_properties()

        bpy.utils.register_class(cls)


def unregister():
    if global_data.offscreen:
        global_data.offscreen.free()
        global_data.offscreen = None

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
