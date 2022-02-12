############### Operators ###############
import bpy, bgl, gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Operator
from . import global_data, functions, class_defines, convertors
from bpy.props import (
    IntProperty,
    StringProperty,
    FloatProperty,
    FloatVectorProperty,
    EnumProperty,
    BoolProperty,
)
import math
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_line_plane, distance_point_to_plane

import functools
import logging

logger = logging.getLogger(__name__)


def draw_selection_buffer(context):
    # Draw elements offscreen
    region = context.region

    # create offscreen
    width, height = region.width, region.height
    offscreen = global_data.offscreen = gpu.types.GPUOffScreen(width, height)

    with offscreen.bind():
        bgl.glClearColor(0.0, 0.0, 0.0, 0.0)
        bgl.glClear(bgl.GL_COLOR_BUFFER_BIT)

        entities = list(context.scene.sketcher.entities.all)
        for e in reversed(entities):
            if e.slvs_index in global_data.ignore_list:
                continue
            if not hasattr(e, "draw_id"):
                continue
            e.draw_id(context)


def ensure_selection_texture(context):
    if not global_data.redraw_selection_buffer:
        return

    draw_selection_buffer(context)
    global_data.redraw_selection_buffer = False


# TODO: Avoid to always update batches and selection texture


def update_elements(context, force=False):
    entities = list(context.scene.sketcher.entities.all)
    msg = ""
    for e in reversed(entities):
        if not hasattr(e, "update"):
            continue
        if not force and not e.is_dirty:
            continue

        msg += "\n - " + str(e) + str(e.is_dirty)
        e.update()

    if msg:
        logger.debug("Update geometry batches:" + msg)


def draw_elements(context):
    for e in context.scene.sketcher.entities.all:
        if hasattr(e, "draw"):
            e.draw(context)


def draw_cb():
    context = bpy.context

    update_elements(context)
    draw_elements(context)

    global_data.redraw_selection_buffer = True


class HighlightElement:
    """
    Mix-in class to highlight the element this operator acts on. The element can
    either be an entity or a constraint. The element has to be specified by an index
    property for entities and additionaly with a type property for constraints.

        index: IntProperty
        type: StringProperty


    Note that this defines the invoke and description functions, an operator that
    defines one of those has to manually make a call to either of the following:

        self.handle_highlight_active(context) -> from invoke()
        cls.handle_highlight_hover(context, properties) -> from description()


    Settings:
    highlight_hover -> highlights the element as soon as the tooltip is shown
    highlight_active -> highlights the element when the operator is invoked
    """

    highlight_hover: BoolProperty(name="Highlight Hover")
    highlight_active: BoolProperty(name="Highlight Hover")

    @classmethod
    def _do_highlight(cls, context, properties):
        if not properties.is_property_set("index"):
            return cls.__doc__

        if hasattr(properties, "type") and properties.is_property_set("type"):
            c = context.scene.sketcher.constraints.get_from_type_index(properties.type, properties.index)
            global_data.highlight_constraint = c
        else:
            global_data.hover = properties.index

        context.area.tag_redraw()
        return cls.__doc__

    def handle_highlight_active(self, context):
        properties = self.properties
        if properties.highlight_active:
            self._do_highlight(context, properties)

    @classmethod
    def handle_highlight_hover(cls, context, properties):
        if properties.highlight_hover:
            cls._do_highlight(context, properties)

    @classmethod
    def description(cls, context, properties):
        cls.handle_highlight_hover(context, properties)

    def invoke(self, context, event):
        self.handle_highlight_active(context)
        return self.execute(context)


class View3D_OT_slvs_register_draw_cb(Operator):
    bl_idname = "view3d.slvs_register_draw_cb"
    bl_label = "Register Draw Callback"

    def execute(self, context):
        global_data.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_cb, (), "WINDOW", "POST_VIEW"
        )

        return {"FINISHED"}


class View3D_OT_slvs_unregister_draw_cb(Operator):
    bl_idname = "view3d.slvs_unregister_draw_cb"
    bl_label = ""

    def execute(self, context):
        global_data.draw_handler.remove_handle()
        return {"FINISHED"}


def deselect_all(context):
    global_data.selected.clear()


def entities_3d(context):
    for e in context.scene.sketcher.entities.all:
        if hasattr(e, "sketch"):
            continue
        yield e


def select_all(context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        generator = sketch.sketch_entities(context)
    else:
        generator = entities_3d(context)

    for e in generator:
        if e.selected:
            continue
        if not e.is_visible(context):
            continue
        if not e.is_active(context.scene.sketcher.active_sketch):
            continue
        e.selected = True


class View3D_OT_slvs_select(Operator, HighlightElement):
    """
    Select an entity

    Either the entity specified by the index property or the hovered index
    if the index property is not set

    """

    bl_idname = "view3d.slvs_select"
    bl_label = "Select Solvespace Entities"

    index: IntProperty(name="Index", default=-1)
    # TODO: Add selection modes

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        index = self.index if self.properties.is_property_set("index") else global_data.hover
        if index != -1:
            entity = context.scene.sketcher.entities.get(index)
            entity.selected = not entity.selected
        else:
            deselect_all(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_select_all(Operator):
    """Select / Deselect all entities"""

    bl_idname = "view3d.slvs_select_all"
    bl_label = "Select / Deselect Entities"

    deselect: BoolProperty(name="Deselect")

    def execute(self, context):
        if self.deselect:
            deselect_all(context)
        else:
            select_all(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_context_menu(Operator, HighlightElement):
    """Show element's settings"""

    bl_idname = "view3d.slvs_context_menu"
    bl_label = "Solvespace Context Menu"

    type: StringProperty(name="Type", options={'SKIP_SAVE'})
    index: IntProperty(name="Index", default=-1, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        is_entity = True
        entity_index = None
        constraint_index = None
        element = None

        # Constraints
        if self.properties.is_property_set("type"):
            constraint_index = self.index
            constraints = context.scene.sketcher.constraints
            element = constraints.get_from_type_index(self.type, self.index)
            is_entity = False
        else:
            # Entities
            entity_index = self.index if self.properties.is_property_set("index") else global_data.hover

            if entity_index != -1:
                element = context.scene.sketcher.entities.get(entity_index)

        def draw_context_menu(self, context):
            col = self.layout.column()

            if not element:
                col.label(text="Nothing hovered")
                return

            col.label(text="Type: " + type(element).__name__)

            if is_entity:
                if functions.get_prefs().show_debug_settings:
                    col.label(text="Index: " + str(element.slvs_index))
                col.label(text="Is Origin: " + str(element.origin))
                col.separator()
                col.prop(element, "visible")
                col.prop(element, "fixed")
                col.prop(element, "construction")

            elif element.failed:
                col.label(text="Failed", icon="ERROR")
            col.separator()

            if hasattr(element, "draw_props"):
                element.draw_props(col)
                col.separator()

            # Delete operator
            if is_entity:
                col.operator(View3D_OT_slvs_delete_entity.bl_idname, icon='X').index = element.slvs_index
            else:
                props = col.operator(View3D_OT_slvs_delete_constraint.bl_idname, icon='X')
                props.type = element.type
                props.index = constraint_index

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}

class View3D_OT_slvs_show_solver_state(Operator):
    """Show details about solver status"""

    bl_idname = "view3d.slvs_show_solver_state"
    bl_label = "Solver Status"

    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        index = self.index
        if index == -1:
            return {"CANCELLED"}

        def draw_item(self, context):
            layout = self.layout
            sketch = context.scene.sketcher.entities.get(index)
            state = sketch.get_solver_state()

            row = layout.row(align=True)
            row.alignment = "LEFT"
            row.label(text=state.name, icon=state.icon)

            layout.separator()
            layout.label(text=state.description)

        context.window_manager.popup_menu(draw_item)
        return {"FINISHED"}


from .solver import Solver, solve_system


class View3D_OT_slvs_solve(Operator):
    bl_idname = "view3d.slvs_solve"
    bl_label = "Solve"

    all: BoolProperty(name="Solve All", options={"SKIP_SAVE"})

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        solver = Solver(context, sketch, all=self.all)
        ok = solver.solve()

        # Keep messages simple, sketches are marked with solvestate
        if ok:
            self.report({"INFO"}, "Successfully solved")
        else:
            self.report({"WARNING"}, "Solver failed")

        context.area.tag_redraw()
        return {"FINISHED"}


def add_point(context, pos, name=""):
    data = bpy.data
    ob = data.objects.new(name, None)
    ob.location = pos
    context.collection.objects.link(ob)
    return ob


class View3D_OT_slvs_tweak(Operator):
    """Tweak the hovered element"""

    bl_idname = "view3d.slvs_tweak"
    bl_label = "Tweak Solvespace Entities"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        index = global_data.hover
        # TODO: hover should be -1 if nothing is hovered, not None!
        if index == None or index == -1:
            return {"CANCELLED"}

        entity = context.scene.sketcher.entities.get(index)
        self.entity = entity

        coords = (event.mouse_region_x, event.mouse_region_y)
        origin, view_vector = functions.get_picking_origin_dir(context, coords)

        if not hasattr(entity, "closest_picking_point"):
            if not hasattr(entity, "sketch"):
                self.report(
                    {"WARNING"}, "Cannot tweak element of type {}".format(type(entity))
                )
                return {"CANCELLED"}

            # For 2D entities it should be enough precise to get picking point from intersection with workplane
            wp = entity.sketch.wp
            coords = (event.mouse_region_x, event.mouse_region_y)
            origin, dir = functions.get_picking_origin_dir(context, coords)
            end_point = dir * context.space_data.clip_end + origin
            pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
        else:
            pos = entity.closest_picking_point(origin, view_vector)

        # find the depth
        self.depth = (pos - origin).length

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            context.window.cursor_modal_restore()
            return {"FINISHED"}

        context.window.cursor_modal_set("HAND")

        if event.type == "MOUSEMOVE":
            entity = self.entity
            coords = (event.mouse_region_x, event.mouse_region_y)

            # Get tweaking position
            origin, dir = functions.get_picking_origin_dir(context, coords)

            if hasattr(entity, "sketch"):
                wp = entity.wp
                end_point = dir * context.space_data.clip_end + origin
                pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
            else:
                pos = dir * self.depth + origin

            sketch = context.scene.sketcher.active_sketch
            solver = Solver(context, sketch)
            solver.tweak(entity, pos)
            retval = solver.solve(report=False)

            # NOTE: There's no blocking cursor
            # also solving frequently returns an error while tweaking which causes flickering
            # if retval != 0:
            # context.window.cursor_modal_set("WAIT")
            # self.report({'WARNING'}, "Cannot solve sketch, error: {}".format(retval))

            context.area.tag_redraw()

        return {"RUNNING_MODAL"}


def write_selection_buffer_image(image_name):
    offscreen = global_data.offscreen
    width, height = offscreen.width, offscreen.height
    buffer = bgl.Buffer(bgl.GL_FLOAT, width * height * 4)
    with offscreen.bind():
        bgl.glReadPixels(0, 0, width, height, bgl.GL_RGBA, bgl.GL_FLOAT, buffer)

    if not image_name in bpy.data.images:
        bpy.data.images.new(image_name, width, height)
    image = bpy.data.images[image_name]
    image.scale(width, height)
    image.pixels = buffer
    return image


class VIEW3D_OT_slvs_write_selection_texture(Operator):
    """Write selection texture to image for debuging"""

    bl_idname = "view3d.slvs_write_selection_texture"
    bl_label = "Write selection texture"

    def execute(self, context):
        if context.area.type != "VIEW_3D":
            self.report({"WARNING"}, "View3D not found, cannot run operator")
            return {"CANCELLED"}

        if not global_data.offscreen:
            self.report({'WARNING'}, "Selection texture is not available")
            return {'CANCELLED'}

        image = write_selection_buffer_image("selection_buffer")
        self.report({"INFO"}, "Wrote buffer to image: {}".format(image.name))

        return {"FINISHED"}


# NOTE: The draw handler has to be registered before this has any effect, currently it's possible that
# entities are first created with an entity that was hovered in the previous state
# Not sure if it's possible to force draw handlers...
# Also note that a running modal operator might prevent redraws, avoid returning running_modal
def ignore_hover(entity):
    ignore_list = global_data.ignore_list
    ignore_list.append(entity.slvs_index)


# TODO: could probably check entity type only through index, instead of getting the entity first...
def get_hovered(context, *types):
    hovered = global_data.hover
    entity = None

    if hovered != -1:
        entity = context.scene.sketcher.entities.get(hovered)
        if type(entity) in types:
            return entity
    return None


def format_types(types):
    entity_names = ", ".join([e.__name__ for e in types])
    return "[" + entity_names + "]"


def state_desc(name, desc, types):
    type_desc = ""
    if types:
        type_desc = "Types: " + format_types(types)
    return " ".join((name + ":", desc, type_desc))


def stateful_op_desc(base, *state_descs):
    states = ""
    length = len(state_descs)
    for i, state in enumerate(state_descs):
        states += " - {}{}".format(
            state, ("  \n" if i < length - 1 else "")
        )
    desc = "{}  \n  \nStates:  \n{}".format(base, states)
    return desc


numeric_events = (
    "ZERO",
    "ONE",
    "TWO",
    "THREE",
    "FOUR",
    "FIVE",
    "SIX",
    "SEVEN",
    "EIGHT",
    "NINE",
    "PERIOD",
    "NUMPAD_0",
    "NUMPAD_1",
    "NUMPAD_2",
    "NUMPAD_3",
    "NUMPAD_4",
    "NUMPAD_5",
    "NUMPAD_6",
    "NUMPAD_7",
    "NUMPAD_8",
    "NUMPAD_9",
    "NUMPAD_PERIOD",
    "MINUS",
    "NUMPAD_MINUS",
)


class StatefulOperator:
    state_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    wait_for_input: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=True)
    continuose_draw: BoolProperty(name="Continuose Draw", default=False)

    executed = False
    _state_data = {}
    _last_coords = Vector((0, 0))
    _numeric_input = {}

    @property
    def state(self):
        return self.states[self.state_index]

    def _index_from_state(self, state):
        return [e.name for e in self.states].index(state)

    @state.setter
    def state(self, state):
        self.state_index = self._index_from_state(state)

    def set_state(self, context, index):
        self.state_index = index
        self.init_numeric(False)
        self.init_substate()
        self.set_status_text(context)

    def next_state(self, context):
        i = self.state_index
        if (i + 1) >= len(self.states):
            return False
        self.set_state(context, i + 1)
        return True

    def set_status_text(self, context):
        # Setup state
        state = self.state
        desc = (
            state.description(self, state)
            if callable(state.description)
            else state.description
        )

        msg = state_desc(state.name, desc, state.types)
        if self.state_data.get("is_numeric_edit", False):
            index = self._substate_index
            prop = self._stateprop
            type = prop.type
            array_length = prop.array_length if prop.array_length else 1
            if type == "FLOAT":
                input = [0.0] * array_length
                for key, val in self._numeric_input.items():
                    input[key] = val

                input[index] = "*" + str(input[index])
                input = str(input).replace('"', "").replace("'", "")
            elif type == "INT":
                input = self.numeric_input

            msg += "    {}: {}".format(prop.subtype, input)

        context.workspace.status_text_set(msg)

    def init_numeric(self, is_numeric):
        self._numeric_input = {}

        # TODO: not when iterating substates
        self.state_data["is_numeric_edit"] = is_numeric
        self._substate_index = 0

    def init_substate(self):
        prop_name = self.state.property
        if prop_name:
            prop = self.properties.rna_type.properties[prop_name]
            self._substate_count = prop.array_length
            self._stateprop = prop
        else:
            self._substate_count = None
            self._stateprop = None

    def iterate_substate(self):
        i = self._substate_index
        if i + 1 >= self._substate_count:
            i = 0
        else:
            i += 1
        self._substate_index = i

    @property
    def numeric_input(self):
        return self._numeric_input.get(self._substate_index, "")

    @numeric_input.setter
    def numeric_input(self, value):
        self._numeric_input[self._substate_index] = value

    def check_event(self, event):
        state = self.state
        if (
            event.type in ("LEFTMOUSE", "RET", "NUMPAD_ENTER")
            and event.value == "PRESS"
        ):
            return True
        if self.state_index == 0 and not self.wait_for_input:
            # Trigger the first state
            return not self.state_data.get("is_numeric_edit", False)
        if state.no_event:
            return True
        return False

    @staticmethod
    def is_numeric_input(event):
        return event.type in (*numeric_events, "BACK_SPACE")

    @staticmethod
    def is_unit_input(event):
        return event.type in (
            "M",
            "K",
            "D",
            "C",
            "U",
            "A",
            "H",
            "I",
            "L",
            "N",
            "F",
            "T",
            "Y",
            "U",
            "R",
            "E",
            "G",
        )

    @staticmethod
    def get_unit_value(event):
        type = event.type
        return type.lower()

    @staticmethod
    def get_value_from_event(event):
        type = event.type
        if type in ("ZERO", "NUMPAD_0"):
            return "0"
        if type in ("ONE", "NUMPAD_1"):
            return "1"
        if type in ("TWO", "NUMPAD_2"):
            return "2"
        if type in ("THREE", "NUMPAD_3"):
            return "3"
        if type in ("FOUR", "NUMPAD_4"):
            return "4"
        if type in ("FIVE", "NUMPAD_5"):
            return "5"
        if type in ("SIX", "NUMPAD_6"):
            return "6"
        if type in ("SEVEN", "NUMPAD_7"):
            return "7"
        if type in ("EIGHT", "NUMPAD_8"):
            return "8"
        if type in ("NINE", "NUMPAD_9"):
            return "9"
        if type in ("PERIOD", "NUMPAD_PERIOD"):
            return "."

    def evaluate_numeric_event(self, event):
        type = event.type
        if type == "BACK_SPACE":
            input = self.numeric_input
            if len(input):
                self.numeric_input = input[:-1]
        elif type in ("MINUS", "NUMPAD_MINUS"):
            input = self.numeric_input
            if input.startswith("-"):
                input = input[1:]
            else:
                input = "-" + input
            self.numeric_input = input
        elif self.is_unit_input(event):
            self.numeric_input += self.get_unit_value(event)
        else:
            self.numeric_input += self.get_value_from_event(event)

    def is_in_previous_states(self, entity):
        i = self.state_index - 1
        while True:
            if i < 0:
                break
            state = self.states[i]
            if state.pointer and entity == getattr(self, state.pointer):
                return True
            i -= 1
        return False

    def prefill_state_props(self, context):
        func = self.state.parse_selection
        selected = context.scene.sketcher.entities.selected_entities

        # Iterate states and try to prefill state props
        while True:
            result = None
            state = self.state

            coords = None

            if not state.allow_prefill:
                break

            elif func:  # Allow overwritting
                result = func(self, selected)

            elif state.pointer:
                # TODO: Discard if too many entities are selected?
                types = state.types
                for i, e in enumerate(selected):
                    if type(e) in types:
                        result = selected.pop(i)
                        break

            if result:
                setattr(self, state.pointer, result)
                self.state_data["is_existing_entity"] = True

                if not self.next_state(context):
                    return {"FINISHED"}
                continue
            break
        return {"RUNNING_MODAL"}

    @property
    def state_data(self):
        return self._state_data.setdefault(self.state_index, {})

    def get_func(self, state, name):
        # fallback to operator method if function isn't specified by state
        func = getattr(state, name, None)
        if func:
            return func
        if hasattr(self, name):
            return getattr(self, name)
        return None

    def invoke(self, context, event):
        self._state_data.clear()
        if hasattr(self, "init"):
            self.init(context, event)

        retval = {"RUNNING_MODAL"}

        go_modal = True
        if self.is_numeric_input(event):
            self.init_numeric(True)
            self.init_substate()
            self.evaluate_numeric_event(event)
            retval = {"RUNNING_MODAL"}
            self.evaluate_state(context, event, False)

        # NOTE: This allows to start the operator but waits for action (LMB event).
        # Try to fill states based on selection only when this is True since it doesn't
        # make senese to respect selection when the user interactivley starts the operator.
        elif self.wait_for_input:
            retval = self.prefill_state_props(context)
            if retval == {"FINISHED"}:
                go_modal = False

            # NOTE: It might make sense to cancle Operator if no prop could be filled
            # Otherwise it might not be obvious that an operator is running
            # if self.state_index == 0:
            #     return self._end(context, False)

            if not self.executed and self.check_props():
                self.run_op(context)
                self.executed = True
            context.area.tag_redraw()  # doesnt seem to work...

        self.set_status_text(context)

        if go_modal:
            context.window_manager.modal_handler_add(self)
            return retval

        succeede = retval == {"FINISHED"}
        if succeede:
            # NOTE: It seems like there's no undo step pushed if an operator finishes from invoke
            # could push an undo_step here however this causes duplicated constraints after redo,
            # disable for now
            # bpy.ops.ed.undo_push()
            pass
        return self._end(context, succeede)

    def run_op(self, context):
        if not hasattr(self, "main"):
            raise NotImplementedError(
                "StatefulOperators need to have a main method defined!"
            )
        retval = self.main(context)
        self.executed = True
        return retval

    # Creates non-persistent data
    def redo_states(self, context):
        for i, state in enumerate(self.states):
            if i > self.state_index:
                # TODO: don't depend on active state, idealy it's possible to go back
                break
            if state.pointer:
                state_data = self._state_data.get(i, {})
                is_existing_entity = state_data["is_existing_entity"]

                if state.property and not is_existing_entity:
                    state = self.states[i]
                    data = self._state_data.get(i, {})
                    create = self.get_func(state, "create_element")
                    entity = create(context, getattr(self, state.property), state, data)
                    setattr(self, state.pointer, entity)

    def execute(self, context):
        self.redo_states(context)
        ok = self.main(context)
        return self._end(context, ok)
        # maybe allow to be modal again?

    def get_numeric_value(self, context, coords):
        state = self.state
        prop_name = state.property
        prop = self.properties.rna_type.properties[prop_name]

        def parse_input(prop, input):
            units = context.scene.unit_settings
            unit = prop.unit
            type = prop.type
            if unit != "NONE":
                try:
                    value = bpy.utils.units.to_value(units.system, unit, input)
                except ValueError:
                    return prop.default
                if type == "INT":
                    value = int(value)
            elif type == "FLOAT":
                value = float(input)
            elif type == "INT":
                value = int(input)
            else:
                value = prop.default
            return value

        if self._substate_count:
            if len(self._numeric_input) < self._substate_count:
                position_cb = self.get_func(state, "state_func")
                result = position_cb(context, coords)
            else:
                result = [0.0] * self._substate_count

            for i, input in self._numeric_input.items():
                if not input:
                    continue
                result[i] = parse_input(prop, input)
        else:
            result = parse_input(prop, self.numeric_input)
        # FIX: result is sometimes a list and sometimes a vector

        # Store input on state
        storage = [None] * self._substate_count
        for i, input in self._numeric_input.items():
            if not input:
                continue
            storage[i] = result[i]
        self.state_data["numeric_input"] = storage

        return result

    def modal(self, context, event):
        state = self.state
        event_triggered = self.check_event(event)
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        is_numeric_edit = self.state_data.get("is_numeric_edit", False)
        is_numeric_event = event.value == "PRESS" and self.is_numeric_input(event)

        if is_numeric_edit:
            if self.is_unit_input(event) and event.value == "PRESS":
                is_numeric_event = True
            elif event.type == "TAB" and event.value == "PRESS":
                self.iterate_substate()
                self.set_status_text(context)
        elif is_numeric_event:
            # Initalize
            self.init_numeric(True)
            self.init_substate()
            is_numeric_edit = True

        if event.type in {"RIGHTMOUSE", "ESC"}:
            return self._end(context, False)

        # HACK: when calling ops.ed.undo() inside an operator a mousemove event
        # is getting triggered. manually check if theres a mousemove...
        mousemove_threshold = 0.1
        is_mousemove = (coords - self._last_coords).length > mousemove_threshold
        self._last_coords = coords

        if not event_triggered:
            if is_numeric_event:
                pass
            elif is_mousemove and is_numeric_edit:
                event_triggered = False
                pass
            elif not state.interactive:
                return {"PASS_THROUGH"}
            elif not is_mousemove:
                return {"PASS_THROUGH"}

        # TODO: Disable numeric input when no state.property
        if is_numeric_event:
            self.evaluate_numeric_event(event)
            self.set_status_text(context)

        return self.evaluate_state(context, event, event_triggered)

    def evaluate_state(self, context, event, triggered):
        state = self.state
        is_numeric = self.state_data.get("is_numeric_edit", False)
        coords = Vector((event.mouse_region_x, event.mouse_region_y))

        # Pick hovered element
        hovered = None
        if not is_numeric and state.pointer:
            pick = self.get_func(state, "pick_element")
            hovered = pick(context, coords)

        # Set state property
        ok = False
        undo = False
        stateprop = None
        if state.property:
            if is_numeric:
                stateprop = self.get_numeric_value(context, coords)
            elif not hovered:
                position_cb = self.get_func(state, "state_func")
                stateprop = position_cb(context, coords)

            if stateprop:
                setattr(self, state.property, stateprop)
                undo = True
                ok = not state.pointer

        # Set state pointer
        pointer = None
        if state.pointer:
            if hovered:
                pointer = hovered
                self.state_data["is_existing_entity"] = True
                undo = True
            elif stateprop:
                # Let pointer be filled from redo_states
                self.state_data["is_existing_entity"] = False
                ok = True

            if pointer:
                setattr(self, state.pointer, pointer)
                ok = True

        if undo:
            bpy.ops.ed.undo_push(message="Redo: " + self.bl_label)
            bpy.ops.ed.undo()
            global_data.ignore_list.clear()
            self.redo_states(context)

        if self.check_props():
            self.run_op(context)

        # Iterate state
        if triggered and ok:
            if not self.next_state(context):
                if self.check_continuose_draw():
                    self.do_continuose_draw(context)
                else:
                    return self._end(context, True)

            if is_numeric:
                # NOTE: Run next state already once even if there's no mousemove yet,
                # This is needed in order for the geometry to update
                self.evaluate_state(context, event, False)
        context.area.tag_redraw()

        if triggered or is_numeric:
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def check_continuose_draw(self):
        if self.continuose_draw:
            if not hasattr(self, "continue_draw") or self.continue_draw():
                return True
        return False

    def _reset_op(self):
        self.executed = False
        self._state_data.clear()
        for s in self.states:
            if not s.pointer:
                continue
            setattr(self, s.pointer, None)

    def do_continuose_draw(self, context):
        # end operator
        self._end(context, True)
        bpy.ops.ed.undo_push(message=self.bl_label)

        # save last prop
        last_pointer = None
        for s in reversed(self.states):
            if not s.pointer:
                continue
            last_pointer = getattr(self, s.pointer)
            break

        # reset operator
        self._reset_op()

        # set first pointer
        setattr(self, self.states[0].pointer, last_pointer)
        self._state_data[0] = {"is_existing_entity": True}
        self.set_state(context, 1)

    def _end(self, context, succeede):
        if hasattr(self, "fini"):
            self.fini(context, succeede)
        global_data.ignore_list.clear()

        context.workspace.status_text_set(None)
        if succeede:
            return {"FINISHED"}
        else:
            bpy.ops.ed.undo_push(message="Cancelled: " + self.bl_label)
            bpy.ops.ed.undo()
            return {"CANCELLED"}

    def check_props(self):
        for state in self.states:
            if state.pointer:
                func = self.get_func(state, "check_pointer")
                if not func(state.pointer):
                    return False
            elif state.property:
                if not self.properties.is_property_set(state.property):
                    return False
        return True

    def draw(self, context):
        layout = self.layout

        for i, state in enumerate(self.states):
            if i != 0:
                layout.separator()

            layout.label(text=state.name)

            state_data = self._state_data.get(i, {})
            is_existing = state_data.get("is_existing_entity", False)
            if state.pointer and is_existing:
                layout.label(text=str(getattr(self, state.pointer)))
            else:
                layout.prop(self, state.property, text="")


# StatefulOperator Doc

# Operator Methods
# main(self, context) -> succeede(bool)
#   function which creates the actual result of the operator,
#   e.g. the main function of an add_line operator creates the line

# check_props(self) -> succeede(bool)
#   additional poll function to check if all neccesary operator properties
#   are set and the main function can be called

# init(self, context, event) -> None

# fini(self, context, succeede) -> None

# check_pointer(self, prop_name) -> is_set(bool)
#   check if a state pointer is set


# State Definition
# state_func(self, context, coords) property_value(ANY)
#   method to get the value for the state property from mouse coordinates

# pick_element(self, context, coords) -> element
#   method to pick a matching element from mouse coordinates to fill the state property

# create_element(self, context, value, state, state_data) -> element
#   method to create state element when no existing element gets picked


from collections import namedtuple

OperatorState = namedtuple(
    "OperatorState",
    (
        "name",  # The name to display in the interface
        "description",  # Text to be displayed in statusbar
        "property",  # Operator property this state acts upon
        # Optional: A state can reference an element, pointer attribute set the name of property function
        # if set this will be passed to main func,
        # state_func should fill main property and create_element should fill this property
        # maybe this could just store it in a normal attr, should work as long as the same operator instance is used, test!
        "pointer",
        "types",  # Types the pointer property can accept
        "no_event",  # Trigger state without an event
        "interactive",  # Always evaluate state and confirm by user input
        "state_func",  # Function to get the state property value from mouse coordinates
        "allow_prefill",  # Define if state should be filled from selected entities when invoked
        "parse_selection",  # Prefill Function which chooses entity to use for this stat
        "pick_element",
        "create_element",
        # TODO: Implement!
        "use_interactive_placemenet",  # Create new state element based on mouse coordinates
        "check_pointer",
    ),
)
del namedtuple


def state_from_args(name, **kwargs):
    """
    Use so each state can avoid defining all members of the named tuple.
    """
    kw = {
        "name": name,
        "description": None,
        "property": None,
        "pointer": None,
        "types": (),
        "no_event": False,
        "interactive": False,
        "state_func": None,
        "allow_prefill": True,
        "parse_selection": None,
        "pick_element": None,
        "create_element": None,
        "use_interactive_placemenet": True,
        "check_pointer": None,
    }
    kw.update(kwargs)
    return OperatorState(**kw)


from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d


class GenericEntityOp:
    def check_pointer(self, prop_name):
        return self.properties.is_property_set(prop_name + "_i")

    def pick_element(self, context, _coords):
        state = self.state
        data = self.state_data

        hovered = get_hovered(context, *state.types)
        if hovered and self.is_in_previous_states(hovered):
            hovered = None

        # Set the hovered entity for constraining if not directly used
        hovered_index = -1
        if not hovered and hasattr(self, "_check_constrain"):
            hover = global_data.hover
            if hover and self._check_constrain(context, hover):
                hovered_index = hover

        data["hovered"] = hovered_index
        return hovered

    def add_coincident(self, context, point, state, state_data):
        index = state_data.get("hovered", -1)
        if index != -1:
            hovered = context.scene.sketcher.entities.get(index)
            constraints = context.scene.sketcher.constraints

            sketch = None
            if hasattr(self, "sketch"):
                sketch = self.sketch
            state_data["coincident"] = constraints.add_coincident(
                point, hovered, sketch=sketch
            )

    def has_coincident(self):
        for state_index, data in self._state_data.items():
            if data.get("coincident", None):
                return True
        return False


class Operator3d(GenericEntityOp):
    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i == -1

    def init(self, context, event):
        pass

    def state_func(self, context, coords):
        return functions.get_placement_pos(context, coords)

    def create_element(self, context, value, state, state_data):
        sse = context.scene.sketcher.entities
        point = sse.add_point_3d(value)
        ignore_hover(point)

        self.add_coincident(context, point, state, state_data)
        return point

    # Check if hovered entity should be constrained
    def _check_constrain(self, context, index):
        type = context.scene.sketcher.entities.type_from_index(index)
        return type in (class_defines.SlvsLine3D, class_defines.SlvsWorkplane)


class Operator2d(GenericEntityOp):
    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i != -1

    def init(self, context, event):
        self.sketch = context.scene.sketcher.active_sketch

    def state_func(self, context, coords):
        wp = self.sketch.wp
        origin, end_point = functions.get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
        pos = wp.matrix_basis.inverted() @ pos
        return Vector(pos[:-1])

    def create_element(self, context, value, state, state_data):
        sse = context.scene.sketcher.entities
        point = sse.add_point_2d(value, self.sketch)
        ignore_hover(point)

        self.add_coincident(context, point, state, state_data)
        return point

    def _check_constrain(self, context, index):
        type = context.scene.sketcher.entities.type_from_index(index)
        return type in (
            class_defines.SlvsLine2D,
            class_defines.SlvsCircle,
            class_defines.SlvsArc,
        )


p3d_state1_doc = ("Location", "Set point's location.")


class View3D_OT_slvs_add_point3d(Operator, Operator3d, StatefulOperator):
    bl_idname = "view3d.slvs_add_point3d"
    bl_label = "Add Solvespace 3D Point"
    bl_options = {"REGISTER", "UNDO"}

    location: FloatVectorProperty(name="Location", subtype="XYZ")

    states = (
        state_from_args(
            p3d_state1_doc[0],
            description=p3d_state1_doc[1],
            property="location",
        ),
    )

    __doc__ = stateful_op_desc(
        "Add a point in 3d space",
        state_desc(*p3d_state1_doc, None),
    )

    def main(self, context):
        self.target = context.scene.sketcher.entities.add_point_3d(self.location)

        # Store hovered entity to use for auto-coincident since it doesnt get
        # stored for non-interactive tools
        hovered = global_data.hover
        if self._check_constrain(context, hovered):
            self.state_data["hovered"] = hovered

        self.add_coincident(context, self.target, self.state, self.state_data)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))


def combined_prop(cls, name, fallback_func, fallback_args, **kwargs):
    class_defines.slvs_entity_pointer(cls, name, **kwargs)

    if not fallback_args:
        return

    annotations = cls.__annotations__.copy()

    if fallback_func:
        fallback_args["name"] = name + "Fallback"
        annotations[name + "_fallback"] = fallback_func(**fallback_args)
    setattr(cls, "__annotations__", annotations)


types_point_3d = (class_defines.SlvsPoint3D,)


l3d_state1_doc = ("Startpoint", "Pick or place line's starting point.")
l3d_state2_doc = ("Endpoint", "Pick or place line's ending point.")


class View3D_OT_slvs_add_line3d(Operator, Operator3d, StatefulOperator):
    bl_idname = "view3d.slvs_add_line3d"
    bl_label = "Add Solvespace 3D Line"
    bl_options = {"REGISTER", "UNDO"}

    continuose_draw: BoolProperty(name="Continuose Draw", default=True)

    states = (
        state_from_args(
            l3d_state1_doc[0],
            description=l3d_state1_doc[1],
            property="p1_fallback",
            pointer="p1",
            types=types_point_3d,
        ),
        state_from_args(
            l3d_state2_doc[0],
            description=l3d_state2_doc[1],
            property="p2_fallback",
            pointer="p2",
            types=types_point_3d,
            interactive=True,
        ),
    )

    __doc__ = stateful_op_desc(
        "Add a line in 3d space",
        state_desc(*l3d_state1_doc, types_point_3d),
        state_desc(*l3d_state2_doc, types_point_3d),
    )

    def main(self, context):
        self.target = context.scene.sketcher.entities.add_line_3d(self.p1, self.p2)
        ignore_hover(self.target)
        return True

    def continue_draw(self):
        last_state = self._state_data[1]
        if last_state["is_existing_entity"]:
            return False

        # also not when last state has coincident constraint
        if last_state.get("coincident"):
            return False
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident:
                solve_system(context)


combined_prop(
    View3D_OT_slvs_add_line3d,
    "p1",
    FloatVectorProperty,
    {"size": 3, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_line3d,
    "p2",
    FloatVectorProperty,
    {"size": 3, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)


wp_state1_doc = ("Origin", "Pick or place workplanes's origin.")
wp_state2_doc = ("Orientation", "Set workplane's orientation.")


class View3D_OT_slvs_add_workplane(Operator, Operator3d, StatefulOperator):
    bl_idname = "view3d.slvs_add_workplane"
    bl_label = "Add Solvespace Workplane"
    bl_options = {"REGISTER", "UNDO"}

    @property
    @functools.cache
    def states(self):
        states = (
            state_from_args(
                wp_state1_doc[0],
                description=wp_state1_doc[1],
                property="p1_fallback",
                pointer="p1",
                types=types_point_3d,
            ),
            state_from_args(
                wp_state2_doc[0],
                description=wp_state2_doc[1],
                property="nm_fallback",
                state_func=self.get_orientation,
                pointer="nm",
                types=(class_defines.SlvsNormal3D,),
                interactive=True,
                create_element=self.create_normal3d,
            ),
        )
        return states

    __doc__ = stateful_op_desc(
        "Add a workplane",
        state_desc(*wp_state1_doc, types_point_3d),
        state_desc(*wp_state2_doc, None),
    )

    def get_orientation(self, context, coords):
        mousepos = functions.get_placement_pos(context, coords)
        vec = mousepos - self.p1.location
        return global_data.Z_AXIS.rotation_difference(vec).to_euler()

    def create_normal3d(self, context, value, state, state_data):
        sse = context.scene.sketcher.entities
        value = value.to_quaternion()
        return sse.add_normal_3d(value)

    def main(self, context):
        self.target = context.scene.sketcher.entities.add_workplane(self.p1, self.nm)
        ignore_hover(self.target)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident:
                solve_system(context)


combined_prop(
    View3D_OT_slvs_add_workplane,
    "p1",
    FloatVectorProperty,
    {"size": 3, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_workplane,
    "nm",
    FloatVectorProperty,
    {
        "size": 3,
        "subtype": "EULER",
        "unit": "ROTATION",
    },
    options={"SKIP_SAVE"},
)

from . import gizmos

sketch_state1_doc = ["Workplane", "Pick a workplane as base for the sketch."]

# TODO:
# - Draw sketches
class View3D_OT_slvs_add_sketch(Operator, Operator3d, StatefulOperator):
    bl_idname = "view3d.slvs_add_sketch"
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    @property
    @functools.cache
    def states(self):
        states = (
            state_from_args(
                sketch_state1_doc[0],
                description=sketch_state1_doc[1],
                pointer="wp",
                types=(class_defines.SlvsWorkplane,),
            ),
        )
        return states

    __doc__ = stateful_op_desc(
        "Add a sketch",
        state_desc(*sketch_state1_doc, (class_defines.SlvsWorkplane,)),
    )

    def ensure_preselect_gizmo(self, context, _coords):
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        if tool.widget != gizmos.VIEW3D_GGT_slvs_preselection.bl_idname:
            bpy.ops.wm.tool_set_by_id(name="sketcher.slvs_select")
        return True

    def prepare_origin_elements(self, context, _coords):
        context.scene.sketcher.entities.ensure_origin_elements(context)
        return True

    def init(self, context, event):
        self.ensure_preselect_gizmo(context, None)
        self.prepare_origin_elements(context, None)
        bpy.ops.ed.undo_push(message="Ensure Origin Elements")
        context.scene.sketcher.show_origin = True

    def main(self, context):
        sse = context.scene.sketcher.entities
        sketch = sse.add_sketch(self.wp)

        # Add point at origin
        # NOTE: Maybe this could create a refrence entity of the main origin?
        p = sse.add_point_2d((0.0, 0.0), sketch)
        p.fixed = True

        context.scene.sketcher.active_sketch = sketch
        self.target = sketch
        return True

    def fini(self, context, succeede):
        context.scene.sketcher.show_origin = False
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            self.wp.visible = False


combined_prop(View3D_OT_slvs_add_sketch, "wp", None, {}, options={"SKIP_SAVE"})

p2d_state1_doc = ("Coordinates", "Set point's coordinates on the sketch.")


class View3D_OT_slvs_add_point2d(Operator, Operator2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_point2d"
    bl_label = "Add Solvespace 2D Point"
    bl_options = {"REGISTER", "UNDO"}

    coordinates: FloatVectorProperty(name="Coordinates", size=2)

    states = (
        state_from_args(
            p2d_state1_doc[0],
            description=p2d_state1_doc[1],
            property="coordinates",
        ),
    )

    __doc__ = stateful_op_desc(
        "Add a point to the active sketch",
        state_desc(*p2d_state1_doc, None),
    )

    def main(self, context):
        sketch = self.sketch
        self.target = context.scene.sketcher.entities.add_point_2d(
            self.coordinates, sketch
        )

        # Store hovered entity to use for auto-coincident since it doesnt get
        # stored for non-interactive tools
        hovered = global_data.hover
        if self._check_constrain(context, hovered):
            self.state_data["hovered"] = hovered

        self.add_coincident(context, self.target, self.state, self.state_data)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident:
                solve_system(context, sketch=self.sketch)


combined_prop(View3D_OT_slvs_add_point2d, "sketch", None, {}, options={"SKIP_SAVE"})


types_point_2d = (class_defines.SlvsPoint2D,)


l2d_state1_doc = ("Startpoint", "Pick or place line's starting Point.")
l2d_state2_doc = ("Endpoint", "Pick or place line's ending Point.")


class View3D_OT_slvs_add_line2d(Operator, Operator2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_line2d"
    bl_label = "Add Solvespace 2D Line"
    bl_options = {"REGISTER", "UNDO"}

    continuose_draw: BoolProperty(name="Continuose Draw", default=True)

    states = (
        state_from_args(
            l2d_state1_doc[0],
            description=l2d_state1_doc[1],
            property="p1_fallback",
            pointer="p1",
            types=types_point_2d,
        ),
        state_from_args(
            l2d_state2_doc[0],
            description=l2d_state2_doc[1],
            property="p2_fallback",
            pointer="p2",
            types=types_point_2d,
            interactive=True,
        ),
    )

    __doc__ = stateful_op_desc(
        "Add a line to the active sketch",
        state_desc(*l2d_state1_doc, types_point_2d),
        state_desc(*l2d_state2_doc, types_point_2d),
    )

    def main(self, context):
        wp = self.sketch.wp
        self.target = context.scene.sketcher.entities.add_line_2d(
            self.p1, self.p2, self.sketch
        )

        # auto vertical/horizontal constraint
        constraints = context.scene.sketcher.constraints
        angle = self.target.direction_vec().angle(Vector((1, 0)))

        threshold = 0.1
        if angle < threshold or angle > math.pi - threshold:
            constraints.add_horizontal(self.target, sketch=self.sketch)
        elif (math.pi / 2 - threshold) < angle < (math.pi / 2 + threshold):
            constraints.add_vertical(self.target, sketch=self.sketch)

        ignore_hover(self.target)
        return True

    def continue_draw(self):
        last_state = self._state_data[1]
        if last_state["is_existing_entity"]:
            return False

        # also not when last state has coincident constraint
        if last_state.get("coincident"):
            return False
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident:
                solve_system(context, sketch=self.sketch)


combined_prop(
    View3D_OT_slvs_add_line2d,
    "p1",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_line2d,
    "p2",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(View3D_OT_slvs_add_line2d, "sketch", None, {}, options={"SKIP_SAVE"})

circle_state1_doc = ("Center", "Pick or place circle's center point.")
circle_state2_doc = ("Radius", "Set circle's radius.")


class View3D_OT_slvs_add_circle2d(Operator, Operator2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_circle2d"
    bl_label = "Add Solvespace 2D Circle"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty(name="Radius", subtype="DISTANCE", unit="LENGTH")

    @property
    @functools.cache
    def states(self):
        states = (
            state_from_args(
                circle_state1_doc[0],
                description=circle_state1_doc[1],
                property="ct_fallback",
                pointer="ct",
                types=types_point_2d,
            ),
            state_from_args(
                circle_state2_doc[0],
                description=circle_state2_doc[1],
                property="radius",
                state_func=self.get_radius,
                interactive=True,
                allow_prefill=False,
            ),
        )
        return states

    __doc__ = stateful_op_desc(
        "Add a circle to the active sketch",
        state_desc(*circle_state1_doc, types_point_2d),
        state_desc(*circle_state2_doc, None),
    )

    def get_radius(self, context, coords):
        wp = self.sketch.wp
        pos = self.state_func(context, coords)

        delta = Vector(pos) - self.ct.co
        radius = delta.length
        return radius

    def main(self, context):
        wp = self.sketch.wp
        self.target = context.scene.sketcher.entities.add_circle(
            wp.nm, self.ct, self.radius, self.sketch
        )
        ignore_hover(self.target)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeede:
            if self.has_coincident:
                solve_system(context, sketch=self.sketch)


combined_prop(
    View3D_OT_slvs_add_circle2d,
    "ct",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(View3D_OT_slvs_add_circle2d, "sketch", None, {}, options={"SKIP_SAVE"})


arc_state1_doc = ("Center", "Pick or place center point.")
arc_state2_doc = ("Startpoint", "Pick or place starting point.")
arc_state3_doc = ("Endpoint", "Pick or place ending point.")


class View3D_OT_slvs_add_arc2d(Operator, Operator2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_arc2d"
    bl_label = "Add Solvespace 2D Arc"
    bl_options = {"REGISTER", "UNDO"}

    @property
    @functools.cache
    def states(self):
        states = (
            state_from_args(
                arc_state1_doc[0],
                description=arc_state1_doc[1],
                property="ct_fallback",
                pointer="ct",
                types=types_point_2d,
            ),
            state_from_args(
                arc_state2_doc[0],
                description=arc_state2_doc[1],
                property="p1_fallback",
                pointer="p1",
                types=types_point_2d,
                allow_prefill=False,
            ),
            state_from_args(
                arc_state3_doc[0],
                description=arc_state3_doc[1],
                property="p2_fallback",
                pointer="p2",
                types=types_point_2d,
                state_func=self.get_endpoint_pos,
                interactive=True,
            ),
        )
        return states

    __doc__ = stateful_op_desc(
        "Add an arc to the active sketch",
        state_desc(*arc_state1_doc, types_point_2d),
        state_desc(*arc_state2_doc, types_point_2d),
        state_desc(*arc_state3_doc, types_point_2d),
    )

    def get_endpoint_pos(self, context, coords):
        mouse_pos = self.state_func(context, coords)

        # Get angle to mouse pos
        ct = self.ct.co
        x, y = Vector(mouse_pos) - ct
        angle = math.atan2(y, x)

        # Get radius from distance ct - p1
        p1 = self.p1.co
        radius = (p1 - ct).length
        pos = functions.pol2cart(radius, angle) + ct
        return pos

    def solve_state(self, context, _event):
        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        return True

    def main(self, context):
        sketch = self.sketch
        sse = context.scene.sketcher.entities
        arc = sse.add_arc(sketch.wp.nm, self.ct, self.p1, self.p2, sketch)

        center = self.ct.co
        start = self.p1.co - center
        end = self.p2.co - center
        a = end.angle_signed(start)
        arc.invert_direction = a < 0

        ignore_hover(arc)
        self.target = arc
        return True

    def fini(self, context, succeede):
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))
            self.solve_state(context, self.sketch)


combined_prop(
    View3D_OT_slvs_add_arc2d,
    "ct",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_arc2d,
    "p1",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_arc2d,
    "p2",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(View3D_OT_slvs_add_arc2d, "sketch", None, {}, options={"SKIP_SAVE"})

rect_state1_doc = ("Startpoint", "Pick or place starting point.")
rect_state2_doc = ("Endpoint", "Pick or place ending point.")


class View3D_OT_slvs_add_rectangle(Operator, Operator2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_rectangle"
    bl_label = "Add Rectangle"
    bl_options = {"REGISTER", "UNDO"}

    @property
    @functools.cache
    def states(self):
        states = (
            state_from_args(
                rect_state1_doc[0],
                description=rect_state1_doc[1],
                property="p1_fallback",
                pointer="p1",
                types=types_point_2d,
            ),
            state_from_args(
                rect_state2_doc[0],
                description=rect_state2_doc[1],
                property="p2_fallback",
                pointer="p2",
                types=types_point_2d,
                interactive=True,
                create_element=self.create_point,
            ),
        )
        return states

    __doc__ = stateful_op_desc(
        "Add a rectangle to the active sketch",
        state_desc(*rect_state1_doc, types_point_2d),
        state_desc(*rect_state1_doc, types_point_2d),
    )

    def main(self, context):
        sketch = self.sketch
        sse = context.scene.sketcher.entities
        p_lb, p_rt = self.p1, self.p2

        p_rb = sse.add_point_2d((p_rt.co.x, p_lb.co.y), sketch)
        p_lt = sse.add_point_2d((p_lb.co.x, p_rt.co.y), sketch)

        lines = []
        points = (p_lb, p_rb, p_rt, p_lt)
        for i, start in enumerate(points):
            end = points[i + 1 if i < len(points) - 1 else 0]

            l = sse.add_line_2d(start, end, sketch)
            lines.append(l)

        self.lines = lines

        for e in (*points, *lines):
            ignore_hover(e)
        return True

    def fini(self, context, succeede):
        if hasattr(self, "lines") and self.lines:
            ssc = context.scene.sketcher.constraints
            for i, line in enumerate(self.lines):
                func = ssc.add_horizontal if (i % 2) == 0 else ssc.add_vertical
                func(line, sketch=self.sketch)

            data = self._state_data.get(1)
            if data.get("is_numeric_edit", False):
                input = data.get("numeric_input")

                # constrain distance
                startpoint = getattr(self, self.states[0].pointer)
                for val, line in zip(input, (self.lines[1], self.lines[2])):
                    if val == None:
                        continue
                    ssc.add_distance(
                        startpoint,
                        line,
                        sketch=self.sketch,
                        init=True,
                    )

        if succeede:
            if self.has_coincident:
                solve_system(context, sketch=self.sketch)

    def create_point(self, context, value, state, state_data):
        if state_data.get("is_numeric_edit", False):
            data = self._state_data.get(1)
            input = data.get("numeric_input")
            # use relative coordinates
            orig = getattr(self, self.states[0].pointer).co

            for i, val in enumerate(input):
                if val == None:
                    continue
                value[i] = orig[i] + val

        sse = context.scene.sketcher.entities
        point = sse.add_point_2d(value, self.sketch)
        ignore_hover(point)

        self.add_coincident(context, point, state, state_data)
        return point


combined_prop(
    View3D_OT_slvs_add_rectangle,
    "p1",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(
    View3D_OT_slvs_add_rectangle,
    "p2",
    FloatVectorProperty,
    {"size": 2, "subtype": "XYZ", "unit": "LENGTH"},
    options={"SKIP_SAVE"},
)
combined_prop(View3D_OT_slvs_add_rectangle, "sketch", None, {}, options={"SKIP_SAVE"})


class View3D_OT_invoke_tool(Operator):
    bl_idname = "view3d.invoke_tool"
    bl_label = "Invoke Tool"

    tool_name: StringProperty(name="Tool ID")

    # TODO: get the operator from tool attribute (tool.bl_operator)?
    operator: StringProperty(name="Operator ID")

    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name=self.tool_name)

        # get the tool operator props
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        props = tool.operator_properties(self.operator)

        options = {}
        for p in props.rna_type.properties.keys():
            if p in ("bl_rna", "rna_type", "state_index"):
                continue
            if p.startswith("_"):
                continue

            default = props.rna_type.properties[p].default
            value = getattr(props, p)

            # NOTE: Setting all values might mess around with operators that check
            # if properties are set. Checking is_property_set here doesn't seem to work.
            # manually check if value is the same as the default however that also
            # seems to fail for vectorproperties and maybe others but prevents
            # the problems from caused by pointer set-state checking...
            if value != default:
                options[p] = value

        options["wait_for_input"] = True

        op_name = self.operator.split(".", 1)
        op = getattr(getattr(bpy.ops, op_name[0]), op_name[1])
        if op.poll():
            op("INVOKE_DEFAULT", **options)
        return {"FINISHED"}


def activate_sketch(context, index, operator):
    props = context.scene.sketcher

    if index == props.active_sketch_i:
        return {"CANCELLED"}

    space_data = context.space_data

    sk = None
    if index != -1:
        sk = context.scene.sketcher.entities.get(index)
        if not sk:
            operator.report({"ERROR"}, "Invalid index: {}".format(index))
            return {"CANCELLED"}

        space_data.show_object_viewport_curve = False
        space_data.show_object_viewport_mesh = False
    else:
        space_data.show_object_viewport_curve = True
        space_data.show_object_viewport_mesh = True

    logger.debug("Activate: {}".format(sk))
    props.active_sketch_i = index

    update_convertor_geometry(context.scene)
    context.area.tag_redraw()
    return {"FINISHED"}


class View3D_OT_slvs_set_active_sketch(Operator):
    """Set the active sketch"""

    bl_idname = "view3d.slvs_set_active_sketch"
    bl_label = "Set active Sketch"
    bl_options = {"UNDO"}

    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        return activate_sketch(context, self.index, self)


def flatten_deps(entity):
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


def is_referenced(entity, context):
    """Check if entity is a dependency of another entity"""
    for e in context.scene.sketcher.entities.all:
        if entity in flatten_deps(e):
            return True
    return False


def get_sketch_deps_indecies(sketch, context):
    deps = []
    for e in context.scene.sketcher.entities.all:
        if not hasattr(e, "sketch_i"):
            continue
        if sketch.slvs_index != e.sketch.slvs_index:
            continue
        deps.append(e.slvs_index)
    return deps


def get_constraint_local_indices(entity, context):
    constraints = context.scene.sketcher.constraints
    ret_list = []

    for data_coll in constraints.get_lists():
        indices = []
        for c in data_coll:
            if entity in c.dependencies():
                indices.append(constraints.get_index(c))
        ret_list.append((data_coll, indices))
    return ret_list


class View3D_OT_slvs_delete_entity(Operator, HighlightElement):
    """Delete Entity by index or based on the selection if index isn't provided
    """
    bl_idname = "view3d.slvs_delete_entity"
    bl_label = "Delete Solvespace Entity"
    bl_options = {"UNDO"}
    bl_description = (
        "Delete Entity by index or based on the selection if index isn't provided"
    )

    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return True

    @staticmethod
    def main(context, index, operator):
        entities = context.scene.sketcher.entities
        entity = entities.get(index)

        if not entity:
            return {"CANCELLED"}

        if isinstance(entity, class_defines.SlvsSketch):
            if context.scene.sketcher.active_sketch_i != -1:
                activate_sketch(context, -1, operator)
            entity.remove_objects()

            deps = get_sketch_deps_indecies(entity, context)
            deps.sort(reverse=True)

            for i in deps:
                operator.delete(entities.get(i), context)

        elif is_referenced(entity, context):
            operator.report(
                {"WARNING"},
                "Cannot delete {}, other entities depend on it.".format(entity),
            )
            return {"CANCELLED"}

        operator.delete(entity, context)

    @staticmethod
    def delete(entity, context):
        # TODO: Some data (Select state, hover, ...) is stored based on index,
        # Clear that data when changing pointers!

        entity.selected = False

        # Delete constraints that depend on entity
        constraints = context.scene.sketcher.constraints

        for data_coll, indices in get_constraint_local_indices(entity, context):
            if not indices:
                continue
            indices.sort(reverse=True)
            for i in indices:
                logger.debug("Delete: {}".format(data_coll[i]))
                data_coll.remove(i)

        logger.debug("Delete: {}".format(entity))
        entities = context.scene.sketcher.entities
        entities.remove(entity.slvs_index)

    def execute(self, context):
        index = self.index

        if index != -1:
            self.main(context, index, self)
        else:
            indices = []
            for e in context.scene.sketcher.entities.selected_entities:
                indices.append(e.slvs_index)

            indices.sort(reverse=True)
            for i in indices:
                e = context.scene.sketcher.entities.get(i)

                # NOTE: this might be slow when alot of entities are selected, improve!
                if is_referenced(e, context):
                    continue
                self.delete(e, context)

        functions.refresh(context)
        return {"FINISHED"}


from .global_data import WpReq

state_docstr = "Pick entity to constrain."


class GenericConstraintOp:
    initialized: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        return True

    @property
    def states(self):
        states = []

        cls = class_defines.SlvsConstraints.cls_from_type(self.type)
        for i, types in enumerate(cls.signature, start=1):
            states.append(
                state_from_args(
                    "Entity " + str(i),
                    description=state_docstr,
                    pointer="entity" + str(i),
                    types=types,
                )
            )
        return states

    def initialize_constraint(self):
        c = self.target
        if not self.initialized and hasattr(c, "init_props"):
            value, setting = c.init_props()
            if value is not None:
                self.value = value
            if setting is not None:
                self.setting = setting
        self.initialized = True

    def check_props(self):
        type = self.type
        cls = class_defines.SlvsConstraints.cls_from_type(type)
        for prop_name in [
            "entity" + str(i) for i, _ in enumerate(range(len(cls.signature)), start=1)
        ]:
            if not self.check_pointer(prop_name):
                return False
        return True

    @classmethod
    def description(cls, context, properties):
        constraint_type = cls.type
        cls = class_defines.SlvsConstraints.cls_from_type(constraint_type)

        states = []
        for i, types in enumerate(cls.signature, start=1):
            states.append(
                state_desc("Entity" + str(i), "Pick entity to constrain.", types)
            )

        return stateful_op_desc("Add {} constraint".format(cls.label), *states)

    def fill_entities(self):
        c = self.target
        args = []
        # fill in entities!
        for prop in ("entity1", "entity2", "entity3", "entity4"):
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
            c.value = self.value
        if hasattr(c, "setting"):
            c.setting = self.setting

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


# Dimensional constarints
class VIEW3D_OT_slvs_add_distance(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_distance"
    bl_label = "Distance"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Distance", subtype="DISTANCE", unit="LENGTH", options={"SKIP_SAVE"}
    )
    type = "DISTANCE"


combined_prop(VIEW3D_OT_slvs_add_distance, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_distance, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_angle(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_angle"
    bl_label = "Angle"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Angle", subtype="ANGLE", unit="ROTATION", options={"SKIP_SAVE"}
    )
    setting: BoolProperty(name="Invert")
    type = "ANGLE"


combined_prop(VIEW3D_OT_slvs_add_angle, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_angle, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_diameter(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_diameter"
    bl_label = "Diameter"
    bl_options = {"UNDO", "REGISTER"}

    value: FloatProperty(
        name="Diameter", subtype="DISTANCE", unit="LENGTH", options={"SKIP_SAVE"}
    )
    type = "DIAMETER"


combined_prop(VIEW3D_OT_slvs_add_diameter, "entity1", None, {}, options={"SKIP_SAVE"})


# Geomteric constraints
class VIEW3D_OT_slvs_add_coincident(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_coincident"
    bl_label = "Coincident"
    bl_options = {"UNDO", "REGISTER"}

    type = "COINCIDENT"


combined_prop(VIEW3D_OT_slvs_add_coincident, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_coincident, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_equal(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_equal"
    bl_label = "Equal"
    bl_options = {"UNDO", "REGISTER"}

    type = "EQUAL"


combined_prop(VIEW3D_OT_slvs_add_equal, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_equal, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_vertical(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_vertical"
    bl_label = "Vertical"
    bl_options = {"UNDO", "REGISTER"}

    type = "VERTICAL"


combined_prop(VIEW3D_OT_slvs_add_vertical, "entity1", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_horizontal(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_horizontal"
    bl_label = "Horizontal"
    bl_options = {"UNDO", "REGISTER"}

    type = "HORIZONTAL"


combined_prop(VIEW3D_OT_slvs_add_horizontal, "entity1", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_parallel(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_parallel"
    bl_label = "Parallel"
    bl_options = {"UNDO", "REGISTER"}

    type = "PARALLEL"


combined_prop(VIEW3D_OT_slvs_add_parallel, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_parallel, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_perpendicular(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_perpendicular"
    bl_label = "Perpendicular"
    bl_options = {"UNDO", "REGISTER"}

    type = "PERPENDICULAR"


combined_prop(
    VIEW3D_OT_slvs_add_perpendicular, "entity1", None, {}, options={"SKIP_SAVE"}
)
combined_prop(
    VIEW3D_OT_slvs_add_perpendicular, "entity2", None, {}, options={"SKIP_SAVE"}
)


class VIEW3D_OT_slvs_add_tangent(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_tangent"
    bl_label = "Tangent"
    bl_options = {"UNDO", "REGISTER"}

    type = "TANGENT"


combined_prop(VIEW3D_OT_slvs_add_tangent, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_tangent, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_midpoint(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):
    bl_idname = "view3d.slvs_add_midpoint"
    bl_label = "Midpoint"
    bl_options = {"UNDO", "REGISTER"}

    type = "MIDPOINT"


combined_prop(VIEW3D_OT_slvs_add_midpoint, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_midpoint, "entity2", None, {}, options={"SKIP_SAVE"})


class VIEW3D_OT_slvs_add_ratio(
    Operator, GenericConstraintOp, StatefulOperator, GenericEntityOp
):

    value: FloatProperty(
        name="Ratio", subtype="UNSIGNED", options={"SKIP_SAVE"}, min=0.0
    )
    bl_idname = "view3d.slvs_add_ratio"
    bl_label = "Ratio"
    bl_options = {"UNDO", "REGISTER"}

    type = "RATIO"


combined_prop(VIEW3D_OT_slvs_add_ratio, "entity1", None, {}, options={"SKIP_SAVE"})
combined_prop(VIEW3D_OT_slvs_add_ratio, "entity2", None, {}, options={"SKIP_SAVE"})


class View3D_OT_slvs_delete_constraint(Operator, HighlightElement):
    """Delete constraint by type and index
    """
    bl_idname = "view3d.slvs_delete_constraint"
    bl_label = "Delete Constraint"
    bl_options = {"UNDO"}
    bl_description = "Delete Constraint"

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return True

    @classmethod
    def description(cls, context, properties):
        cls.handle_highlight_hover(context, properties)
        if properties.type:
            return "Delete: " + properties.type.capitalize()
        return ""

    def execute(self, context):
        constraints = context.scene.sketcher.constraints

        # NOTE: It's not really neccesary to first get the
        # constraint from it's index before deleting

        constr = constraints.get_from_type_index(self.type, self.index)
        logger.debug("Delete: {}".format(constr))

        constraints.remove(constr)

        sketch = context.scene.sketcher.active_sketch
        solve_system(context, sketch=sketch)
        functions.refresh(context)
        return {"FINISHED"}


class View3D_OT_slvs_tweak_constraint_value_pos(Operator):
    bl_idname = "view3d.slvs_tweak_constraint_value_pos"
    bl_label = "Tweak Constraint"
    bl_options = {"UNDO"}
    bl_description = "Tweak constraint's value or display position"

    type: StringProperty(name="Type")
    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        self.tweak = False
        self.init_mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
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

    def execute(self, context):
        bpy.ops.view3d.slvs_context_menu(type=self.type, index=self.index)
        return {"FINISHED"}


from bl_operators.presets import AddPresetBase


class SKETCHER_OT_add_preset_theme(AddPresetBase, Operator):
    """Add an Theme Preset"""

    bl_idname = "bgs.theme_preset_add"
    bl_label = "Add Theme Preset"
    preset_menu = "SKETCHER_MT_theme_presets"

    preset_defines = [
        'prefs = bpy.context.preferences.addons["geometry_sketcher"].preferences',
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


def update_convertor_geometry(scene):
    for sketch in scene.sketcher.entities.sketches:
        if sketch.convert_type == "NONE":
            continue

        data = bpy.data
        name = sketch.name
        mode = sketch.convert_type

        # Convert geometry to curve data
        if mode in ("BEZIER", "MESH"):
            conv = convertors.BezierConvertor(scene, sketch)
            conv.run()

            # TODO: Avoid re-converting sketches where nothing has changed!
            logger.info("Convert sketch {} to {}: ".format(sketch, mode.lower()))

            if not sketch.target_curve:
                curve_data = bpy.data.objects.data.curves.new(name, "CURVE")
                sketch.target_curve = curve_data
            else:
                curve_data = sketch.target_curve
                curve_data.splines.clear()

            conv.to_bezier(curve_data)
            data = curve_data
        else:
            pass

        # Create curve object
        if not sketch.target_curve_object:
            object = bpy.data.objects.new(name, curve_data)
            sketch.target_curve_object = object

        if scene.collection.objects.get(sketch.target_curve_object.name):
            if mode != "BEZIER":
                scene.collection.objects.unlink(sketch.target_curve_object)
        else:
            if mode == "BEZIER":
                scene.collection.objects.link(sketch.target_curve_object)

        if mode == "MESH":
            # Create mesh data
            me = sketch.target_curve_object.to_mesh()
            sketch.target_mesh = me.copy() if me else bpy.data.meshes.new(name)

            # Create mesh object
            if not sketch.target_object:
                object = bpy.data.objects.new(name, sketch.target_mesh)
                scene.collection.objects.link(object)
                sketch.target_object = object
            else:
                sketch.target_object.data = sketch.target_mesh

        if sketch.target_object and mode in ("NONE", "BEZIER"):
            bpy.data.objects.remove(sketch.target_object, do_unlink=True)

        if sketch.target_curve_object and mode == "NONE":
            bpy.data.objects.remove(sketch.target_curve_object, do_unlink=True)

        object = sketch.target_object if mode == "MESH" else sketch.target_curve_object
        object.matrix_world = sketch.wp.matrix_basis


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

classes = (
    View3D_OT_slvs_register_draw_cb,
    View3D_OT_slvs_unregister_draw_cb,
    View3D_OT_slvs_select,
    View3D_OT_slvs_select_all,
    View3D_OT_slvs_context_menu,
    View3D_OT_slvs_show_solver_state,
    View3D_OT_slvs_tweak,
    View3D_OT_slvs_add_point3d,
    VIEW3D_OT_slvs_write_selection_texture,
    View3D_OT_slvs_add_line3d,
    View3D_OT_slvs_add_workplane,
    View3D_OT_slvs_add_sketch,
    View3D_OT_slvs_add_point2d,
    View3D_OT_slvs_add_line2d,
    View3D_OT_slvs_add_circle2d,
    View3D_OT_slvs_add_arc2d,
    View3D_OT_slvs_add_rectangle,
    View3D_OT_invoke_tool,
    View3D_OT_slvs_set_active_sketch,
    View3D_OT_slvs_delete_entity,
    *constraint_operators,
    View3D_OT_slvs_solve,
    View3D_OT_slvs_delete_constraint,
    View3D_OT_slvs_tweak_constraint_value_pos,
    SKETCHER_OT_add_preset_theme,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
