############### Operators ###############
import bpy, bgl, gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Operator
from . import global_data, functions, class_defines, ui, convertors
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

import logging

logger = logging.getLogger(__name__)


# NOTE: Drawing offscreen from 3D View drawhandler might be considered bad practice
# however view projection matrix is already correct
def draw_selection_buffer(context):
    # Draw elements offscreen
    offscreen = global_data.offscreen

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


def draw_elements(context):
    for e in context.scene.sketcher.entities.all:
        if hasattr(e, "update"):
            e.update()  # bad!
        if hasattr(e, "draw"):
            e.draw(context)


def draw_cb():
    context = bpy.context
    offscr = global_data.offscreen
    region = context.region
    if not offscr or region.width != offscr.width or region.height != offscr.height:
        # create offscreen
        width, height = region.width, region.height
        global_data.offscreen = gpu.types.GPUOffScreen(width, height)

    # Draw on screen
    draw_elements(context)
    draw_selection_buffer(context)


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


def refresh(context):
    # update gizmos!
    context.space_data.show_gizmo = True
    context.area.tag_redraw()


def deselect_all(context):
    for e in context.scene.sketcher.entities.all:
        if e.selected:
            e.selected = False


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
        if not e.visible:
            continue
        e.selected = True


class View3D_OT_slvs_select(Operator):
    """Select the hovered Solvespace entity, draw callback has to be already registered..."""

    bl_idname = "view3d.slvs_select"
    bl_label = "Select Solvespace Entities"
    bl_options = {"UNDO"}

    # TODO: Add selection modes

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        index = global_data.hover
        if index != None:
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
    bl_options = {"UNDO"}

    deselect: BoolProperty(name="Deselect")

    def execute(self, context):
        if self.deselect:
            deselect_all(context)
        else:
            select_all(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_context_menu(Operator):
    """Spawn context menu for hovered entity"""

    bl_idname = "view3d.slvs_context_menu"
    bl_label = "Solvespace Context Menu"

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        bpy.ops.wm.call_menu(name=ui.VIEW3D_MT_context_menu.bl_idname)
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

    def execute(self, context):
        solver = Solver(context)
        solver.solve()

        if solver.ok:
            self.report({"INFO"}, solver.result.description)
        else:
            self.report({"WARNING"}, solver.result.description)

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

            if isinstance(entity, class_defines.SlvsArc):
                # NOTE: Coincident isn't supported with arcs, so it doesn't work with current solution
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

            solver = Solver(context)
            solver.tweak(entity, pos)
            retval = solver.solve()

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
    """Generate an offscreen texture for selection"""

    bl_idname = "view3d.slvs_write_selection_texture"
    bl_label = "Write selection texture"

    def execute(self, context):
        if context.area.type != "VIEW_3D":
            self.report({"WARNING"}, "View3D not found, cannot run operator")
            return {"CANCELLED"}

        image = write_selection_buffer_image("selection_buffer")
        self.report({"INFO"}, "Wrote buffer to image: {}".format(image.name))

        return {"FINISHED"}


# NOTE: The draw handler has to be registered before this has any effect, currently it's possible that
# entities are first created with an entity that was hovered in the previous state
# Not sure if it's possible to force draw handlers...
# Also note that a running modal operator might prevent redraws, avoid returning running_modal
def ignore_hover(entity):
    global_data.ignore_list.append(entity.slvs_index)


# TODO: could probably check entity type only through index, instead of getting the entity first...
def get_hovered(context, *types):
    hovered = global_data.hover
    entity = None

    if hovered and hovered != -1:
        entity = context.scene.sketcher.entities.get(hovered)
        if type(entity) in types:
            return entity
    return None


def check_attr(parent, attr):
    return hasattr(parent, attr) and getattr(parent, attr) != None


# TODO: Constrain new point to hovered entity
def pick_place_point(self, context, event, is_2d):
    sse = context.scene.sketcher.entities
    state = self.state
    coords = event.mouse_region_x, event.mouse_region_y
    entity = None
    is_prop_set = self.is_state_prop_set()
    is_existing_entity = state.custom_data.get("is_existing_entity", True)

    hovered = get_hovered(
        context, (class_defines.SlvsPoint2D if is_2d else class_defines.SlvsPoint3D)
    )
    # Workaround for delayed ignore_list update
    if hovered and self.is_in_previous_states(hovered):
        hovered = None

    if hovered:
        entity = hovered
        if is_prop_set and not is_existing_entity:
            sse.remove(
                getattr(self, state.property).slvs_index
            )  # index stays in hover ignore list...
            state.custom_data["is_existing_entity"] = True
    else:
        pos = self.get_placement_pos(context, coords)
        if not is_prop_set or is_existing_entity:
            # Create new point
            entity = self.create_point(context, coords)
            ignore_hover(entity)
        else:
            # Tweak pos of existing entity
            entity = getattr(self, state.property)
            self.tweak_point(entity, pos)

        self.state.custom_data["is_existing_entity"] = False

    context.area.tag_redraw()
    return entity


def set_radius(self, context, event):  # rename get_radius
    coords = event.mouse_region_x, event.mouse_region_y
    wp = self.sketch.wp
    pos = self.get_placement_pos(context, coords)

    delta = Vector(pos) - self.ct.co
    radius = delta.length

    context.area.tag_redraw()
    return radius


def is_slvs_entity_pointer(parent, prop_name):
    # TODO: Improve! maybe entity pointer properties can be marked somehow
    # NOTE: How to check operator properties e.g. its type and default

    prop = getattr(parent, prop_name)
    index_prop_name = prop_name + "_i"

    if not hasattr(parent, index_prop_name):
        return False
    if not isinstance(getattr(parent, index_prop_name), int):
        return False
    return True


class StatefulOperator:
    state_index: IntProperty(options={"HIDDEN", "SKIP_SAVE"})
    wait_for_input: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=True)
    executed = False

    @property
    def state(self):
        return self.states[self.state_index]

    def _index_from_state(self, state):
        return [e.name for e in self.states].index(state)

    @state.setter
    def state(self, state):
        self.state_index = self._index_from_state(state)

    def next_state(self):
        i = self.state_index
        if (i + 1) >= len(self.states):
            return False
        self.state_index += 1
        return True

    def check_event(self, event):
        state = self.state
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            return True
        if self.state_index == 0 and not self.wait_for_input:
            return True
        if state.no_event:
            return True
        return False

    def is_in_previous_states(self, entity):
        i = self.state_index - 1
        while True:
            if i < 0:
                break
            state = self.states[i]
            if state.property and entity == getattr(self, state.property):
                return True
            i -= 1
        return False

    def is_slvs_entity_pointer(self):
        prop_name = self.state.property
        if not prop_name:
            return False

        return is_slvs_entity_pointer(self, prop_name)

    def prefill_state_props(self, context):
        func = self.state.parse_selection
        selected = context.scene.sketcher.entities.selected_entities

        # Iterate states and try to prefill state props
        while True:
            result = None

            if not self.state.allow_prefill:
                break

            elif func:  # Allow overwritting
                result = func(self, selected)

            elif self.is_slvs_entity_pointer():
                prop_name = self.state.property
                # TODO: Discard if too many entities are selected?
                types = self.state.types
                for i, e in enumerate(selected):
                    if type(e) in types:
                        result = selected.pop(i)
                        break

            if result:
                setattr(self, prop_name, result)

                if not self.next_state():
                    return {"FINISHED"}
                continue
            break
        return {"RUNNING_MODAL"}

    def is_state_prop_set(self):
        if self.is_slvs_entity_pointer():
            prop_name = self.state.property + "_i"
        else:
            prop_name = self.state.property
        return self.properties.is_property_set(prop_name)

    def invoke(self, context, event):
        if hasattr(self, "init"):
            self.init(context, event)
        retval = {"RUNNING_MODAL"}
        if self.wait_for_input:
            retval = self.prefill_state_props(context)

            # NOTE: It might make sens to cancle Operator if no prop could be filled
            # Otherwise it might not be obvious that an operator is running
            # if self.state_index == 0:
            #     return self._end(context, event, False)

            if (
                not self.executed
                and hasattr(self, "check_props")
                and self.check_props()
            ):
                self.execute(context)
                self.executed = True
            context.area.tag_redraw()  # doesnt seem to work...

        if retval == {"RUNNING_MODAL"}:
            context.window_manager.modal_handler_add(self)
        return retval

    def modal(self, context, event):
        state = self.state
        event_triggered = self.check_event(event)

        if event.type in {"RIGHTMOUSE", "ESC"}:
            return self._end(context, event, False)

        desc = (
            state.description(self, state)
            if callable(state.description)
            else state.description
        )
        context.workspace.status_text_set("{}: {}".format(state.name, desc))

        if not event_triggered and not state.confirm:
            return {"PASS_THROUGH"}

        args = ()

        # NOTE: function should return the result to assign to the property
        # return None to stay in current state
        # if no property is set, False will stay in the current state True will iterate

        if state.func:
            func = state.func
            if state.args:
                args = state.args

        elif self.is_slvs_entity_pointer():
            args = (True,) if self.is_2d else (False,)
            func = pick_place_point

        # Run function to set property
        result = func(self, context, event, *args)
        # TODO: How to deal with the case when the function cant return something?

        # Set result
        # TODO: only set if not already the same, create func: ensure prop
        if state.property and result:
            if hasattr(self, "target") and self.target:
                setattr(self.target, self.state.property, result)
            setattr(self, self.state.property, result)

        # Execute Operator
        if not self.executed and hasattr(self, "check_props") and self.check_props():
            self.execute(context)
            self.executed = True

        if event_triggered and result:
            # Iterate State
            if not self.next_state():
                return self._end(context, event, True)

        context.area.tag_redraw()

        if event_triggered:
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def _end(self, context, event, succeede):
        if hasattr(self, "fini"):
            self.fini(context, event)
        global_data.ignore_list.clear()

        # NOTE: Is this really needed?
        for s in self.states:
            s.custom_data.clear()

        context.workspace.status_text_set(None)
        if succeede:
            return {"FINISHED"}
        else:
            return {"CANCELLED"}

    def check_props(self):
        for prop_name in dir(self.properties):
            if not prop_name.endswith("_i"):
                continue
            if not self.properties.is_property_set(prop_name):
                return False
        return True


from collections import namedtuple

OperatorState = namedtuple(
    "OperatorState",
    (
        "name",  # The name to display in the interface
        "description",  # Text to be displayed in statusbar
        "property",  # Operator property this state acts upon
        "types",  # Entity types the property can accept
        "no_event",  # Trigger state without an event
        "confirm",  # Trigger action or confirm modification
        "func",  # Function to get value for state property
        "args",  # Arguments to pass to state function
        "allow_prefill",  # Define if state should be filled from selected entities when invoked
        "parse_selection",  # Prefill Function which chooses entity to use for this state
        "custom_data",  # Allow saving data on the state
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
        "types": (),
        "no_event": False,
        "confirm": False,
        "func": None,
        "args": None,
        "allow_prefill": True,
        "parse_selection": None,
        "custom_data": {},
    }
    kw.update(kwargs)
    return OperatorState(**kw)


from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d


class Operator_3d:
    is_2d = False

    def init(self, context, event):
        pass

    def get_placement_pos(self, context, coords):
        return functions.get_placement_pos(context, coords)

    def create_point(self, context, coords):
        sse = context.scene.sketcher.entities
        pos = self.get_placement_pos(context, coords)
        return sse.add_point_3d(pos)

    @staticmethod
    def tweak_point(point, pos):
        point.location = pos


class View3D_OT_slvs_add_point3d(Operator, Operator_3d):
    bl_idname = "view3d.slvs_add_point3d"
    bl_label = "Add Solvespace 3D Point"
    bl_options = {"REGISTER", "UNDO"}

    location: FloatVectorProperty(name="Location", subtype="XYZ")

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i == -1

    def invoke(self, context, event):
        coords = event.mouse_region_x, event.mouse_region_y
        self.location = self.get_placement_pos(context, coords)
        return self.execute(context)

    def execute(self, context):
        p = context.scene.sketcher.entities.add_point_3d(self.location)
        logger.debug("Add: {}".format(p))
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_add_line3d(Operator, Operator_3d, StatefulOperator):
    bl_idname = "view3d.slvs_add_line3d"
    bl_label = "Add Solvespace 3D Line"
    bl_options = {"REGISTER", "UNDO"}

    states = (
        state_from_args(
            "PICK_p1",
            description="Pick or place line's starting point",
            property="p1",
            types=(class_defines.SlvsPoint3D,),
        ),
        state_from_args(
            "PICK_p2",
            description="Pick or place line's ending point",
            property="p2",
            types=(class_defines.SlvsPoint3D,),
            confirm=True,
        ),
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        self.target = context.scene.sketcher.entities.add_line_3d(self.p1, self.p2)
        logger.debug("Add: {}".format(self.target))
        ignore_hover(self.target)
        context.area.tag_redraw()
        return {"FINISHED"}


class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_line3d, "p1", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_line3d, "p2", options={"SKIP_SAVE"}
)


class View3D_OT_slvs_add_workplane(Operator):
    bl_idname = "view3d.slvs_add_workplane"
    bl_label = "Add Solvespace Workplane"
    bl_options = {"REGISTER", "UNDO"}

    orientation: FloatVectorProperty(subtype="EULER")

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        # Get selected objects
        entities = context.scene.sketcher.entities.selected_entities

        origin = None
        for e in entities:
            if isinstance(e, class_defines.SlvsPoint3D):
                origin = e
                break

        if not origin:
            self.report({"WARNING"}, "No point selected")
            return {"CANCELLED"}

        sse = context.scene.sketcher.entities
        nm = sse.add_normal_3d(self.orientation.to_quaternion())
        logger.debug("Add: {}".format(nm))

        wp = sse.add_workplane(origin, nm)
        logger.debug("Add: {}".format(nm))

        context.area.tag_redraw()
        return {"FINISHED"}


def pick_workplane(self, context, event):
    sse = context.scene.sketcher.entities
    state = self.state
    coords = event.mouse_region_x, event.mouse_region_y
    entity = None
    is_prop_set = self.is_state_prop_set()
    is_existing_entity = state.custom_data.get("is_existing_entity", True)

    hovered = get_hovered(context, class_defines.SlvsWorkplane)
    return hovered


def ensure_preselect_gizmo(self, context, event):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool.widget != gizmos.VIEW3D_GGT_slvs_preselection.bl_idname:
        bpy.ops.wm.tool_set_by_id(name="sketcher.slvs_select")
    return True


def prepare_origin_elements(self, context, event):
    context.scene.sketcher.entities.ensure_origin_elements(context)
    context.scene.sketcher.show_origin = True
    return True


from . import gizmos

# TODO:
# - Draw sketches and auto hide wp when creating a sketch on them
class View3D_OT_slvs_add_sketch(Operator, Operator_3d, StatefulOperator):
    """Add a sketch"""

    bl_idname = "view3d.slvs_add_sketch"
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    states = (
        state_from_args("ENSURE_select", func=ensure_preselect_gizmo, no_event=True),
        state_from_args("SHOW_origin", func=prepare_origin_elements, no_event=True),
        state_from_args(
            "PICK_wp",
            description="Pick a workplane as base for the sketch",
            property="wp",
            types=(class_defines.SlvsWorkplane,),
            func=pick_workplane,
        ),
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        sse = context.scene.sketcher.entities
        self.target = sse.add_sketch(self.wp)

        # Add point at origin
        # NOTE: Maybe this could create a refrence entity of the main origin?
        p = sse.add_point_2d((0.0, 0.0), self.target)
        p.fixed = True

        logger.debug("Add: {}".format(self.target))
        context.scene.sketcher.active_sketch = self.target
        context.area.tag_redraw()
        return {"FINISHED"}

    def fini(self, context, event):
        context.scene.sketcher.show_origin = False


class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_sketch, "wp", options={"SKIP_SAVE"}
)


class Operator_2d:
    is_2d = True

    def init(self, context, event):
        self.sketch = context.scene.sketcher.active_sketch

    def get_placement_pos(self, context, coords):
        wp = self.sketch.wp
        origin, end_point = functions.get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, wp.p1.location, wp.normal)
        pos = wp.matrix_basis.inverted() @ pos
        return pos[:-1]

    def entity_from_coords(self, context, sketch, coords, types=()):
        hovered = global_data.hover
        if hovered and hovered != -1:
            entity = context.scene.sketcher.entities.get(hovered)
            if type(entity) in types or not types:
                return entity

        # create new point
        pos = self.get_placement_pos(context, coords)
        return context.scene.sketcher.entities.add_point_2d(pos, sketch)

    def create_point(self, context, coords):
        sse = context.scene.sketcher.entities
        pos = self.get_placement_pos(context, coords)
        return sse.add_point_2d(pos, self.sketch)

    @staticmethod
    def tweak_point(point, pos):
        point.co = pos


from mathutils import Vector


class View3D_OT_slvs_add_point2d(Operator, Operator_2d):
    bl_idname = "view3d.slvs_add_point2d"
    bl_label = "Add Solvespace 2D Point"
    bl_options = {"REGISTER", "UNDO"}

    location: FloatVectorProperty(name="Location", size=2)

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i != -1

    def invoke(self, context, event):
        self.init(context, event)
        coords = event.mouse_region_x, event.mouse_region_y
        sketch = context.scene.sketcher.active_sketch
        self.location = self.get_placement_pos(context, coords)

        self.execute(context)
        return {"FINISHED"}

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch

        p = context.scene.sketcher.entities.add_point_2d(self.location, sketch)
        logger.debug("Add: {}".format(p))
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_add_line2d(Operator, Operator_2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_line2d"
    bl_label = "Add Solvespace 2D Line"
    bl_options = {"REGISTER", "UNDO"}

    states = (
        state_from_args(
            "PICK_p1",
            description="Pick or place line's starting Point",
            property="p1",
            types=(class_defines.SlvsPoint2D,),
        ),
        state_from_args(
            "PICK_p2",
            description="Pick or place line's ending Point",
            property="p2",
            types=(class_defines.SlvsPoint2D,),
            confirm=True,
        ),
    )

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i != -1

    def execute(self, context):
        wp = self.sketch.wp
        self.target = context.scene.sketcher.entities.add_line_2d(
            self.p1, self.p2, self.sketch
        )
        ignore_hover(self.target)
        logger.debug("Add: {}".format(self.target))
        context.area.tag_redraw()
        return {"FINISHED"}


class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_line2d, "p1", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_line2d, "p2", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_line2d, "sketch", options={"SKIP_SAVE"}
)


class View3D_OT_slvs_add_circle2d(Operator, Operator_2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_circle2d"
    bl_label = "Add Solvespace 2D Circle"
    bl_options = {"REGISTER", "UNDO"}

    radius: FloatProperty()

    states = (
        state_from_args(
            "PICK_ct",
            description="Pick or place circle's center point",
            property="ct",
            types=(class_defines.SlvsPoint2D,),
        ),
        state_from_args(
            "SET_radius",
            description="Set circle's radius",
            property="radius",
            func=set_radius,
            confirm=True,
            allow_prefill=False,
        ),
    )

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i != -1

    def execute(self, context):
        wp = self.sketch.wp
        self.target = context.scene.sketcher.entities.add_circle(
            wp.nm, self.ct, self.radius, self.sketch
        )
        ignore_hover(self.target)
        logger.debug("Add: {}".format(self.target))
        context.area.tag_redraw()
        return {"FINISHED"}


class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_circle2d, "ct", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_circle2d, "sketch", options={"SKIP_SAVE"}
)


def solve_state(self, context, _event):
    solve_system(context)
    return True


def set_endpoint(self, context, event):
    sse = context.scene.sketcher.entities
    coords = event.mouse_region_x, event.mouse_region_y
    state = self.state
    pos = self.get_placement_pos(context, coords)

    # Get angle to mouse pos
    ct = self.ct.co
    x, y = Vector(pos) - ct
    angle = math.atan2(y, x)

    # Get radius from distance ct - start
    p1 = self.start.co
    radius = (p1 - ct).length

    pos = Vector(functions.pol2cart(radius, angle)) + ct

    is_prop_set = self.is_state_prop_set()
    is_existing_entity = state.custom_data.get("is_existing_entity", True)

    hovered = get_hovered(context, class_defines.SlvsPoint2D)
    # TODO: check if radius to hovered entity is too different to expected radius from startpoint

    if hovered:
        entity = hovered
        if is_prop_set and not is_existing_entity:
            sse.remove(getattr(self, state.property).slvs_index)
            state.custom_data["is_existing_entity"] = True
    else:
        if not is_prop_set or is_existing_entity:
            # Create new point
            entity = sse.add_point_2d(pos, self.sketch)
            ignore_hover(entity)
        else:
            # Tweak pos of existing entity
            entity = getattr(self, state.property)
            entity.co = pos
        state.custom_data["is_existing_entity"] = False

    context.area.tag_redraw()
    return entity


# NOTE: Operator should probably have an angle prop and place the endpoint based on that,
# however it should also be possible to pick a entity as endpoint...


class View3D_OT_slvs_add_arc2d(Operator, Operator_2d, StatefulOperator):
    bl_idname = "view3d.slvs_add_arc2d"
    bl_label = "Add Solvespace 2D Arc"
    bl_options = {"REGISTER", "UNDO"}

    states = (
        state_from_args(
            "PICK_ct",
            description="Pick or place arc's center point",
            property="ct",
            types=(class_defines.SlvsPoint2D,),
        ),
        state_from_args(
            "PICK_start",
            description="Pick or place arc's starting point",
            property="start",
            allow_prefill=False,
        ),
        state_from_args(
            "SET_end",
            description="Pick or place arc's ending point",
            property="end",
            func=set_endpoint,
            confirm=True,
        ),
        state_from_args("SOLVE", no_event=True, func=solve_state),
    )

    # TODO: Allow to define states which get executed without any event

    @classmethod
    def poll(cls, context):
        return context.scene.sketcher.active_sketch_i != -1

    def execute(self, context):
        sketch = context.scene.sketcher.active_sketch
        wp = sketch.wp

        sse = context.scene.sketcher.entities

        self.target = sse.add_arc(sketch.wp.nm, self.ct, self.start, self.end, sketch)
        ignore_hover(self.target)
        logger.debug("Add: {}".format(self.target))
        context.area.tag_redraw()
        return {"FINISHED"}


class_defines.slvs_entity_pointer(View3D_OT_slvs_add_arc2d, "ct", options={"SKIP_SAVE"})
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_arc2d, "start", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_arc2d, "end", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    View3D_OT_slvs_add_arc2d, "sketch", options={"SKIP_SAVE"}
)


class View3D_OT_invoke_tool(Operator):
    bl_idname = "view3d.invoke_tool"
    bl_label = "Invoke Tool"

    tool: StringProperty()
    operator: StringProperty()

    def execute(self, context):
        bpy.ops.wm.tool_set_by_id(name=self.tool)
        # context.workspace.tools[self.name].operator

        op_name = self.operator.split(".", 1)
        op = getattr(getattr(bpy.ops, op_name[0]), op_name[1])
        if op.poll():
            op("INVOKE_DEFAULT", wait_for_input=True)

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
    """Set active Sketch"""

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


class View3D_OT_slvs_delete_entity(Operator):
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

        refresh(context)
        return {"FINISHED"}


def pick_entity(self, context, event):
    types = self.state.types
    # Get the allowed types for the state property
    hovered = get_hovered(context, *types)
    if hovered:
        ignore_hover(hovered)
        return hovered
    return None


from .global_data import WpReq


class VIEW3D_OT_slvs_add_constraint(Operator, StatefulOperator):
    """Add Solvespace Constraint"""

    bl_idname = "view3d.slvs_add_constraint"
    bl_label = "Add Solvespace Constraint"
    bl_options = {"UNDO", "REGISTER"}

    type: EnumProperty(items=class_defines.constraint_types, options={"SKIP_SAVE"})
    value: FloatProperty(options={"SKIP_SAVE"})
    setting: BoolProperty(options={"SKIP_SAVE"})
    initialized: BoolProperty(options={"SKIP_SAVE"})

    @property
    def states(self):
        states = []
        constraint_type = self.type
        cls = class_defines.SlvsConstraints.cls_from_type(constraint_type)
        for i, types in enumerate(cls.signature, start=1):
            entitie_names = [e.__name__ for e in types]
            states.append(
                state_from_args(
                    "PICK_ENTITY_" + str(i),
                    description="Pick entity to constrain, can be any of type: {} ".format(
                        str(entitie_names)
                    ),
                    property="entity" + str(i),
                    types=types,
                    func=pick_entity,
                )
            )
        return states

    def check_props(self):
        type = self.type
        cls = class_defines.SlvsConstraints.cls_from_type(type)
        for prop_name in [
            "entity" + str(i) for i, _ in enumerate(range(len(cls.signature)), start=1)
        ]:
            if getattr(self, prop_name + "_i") == -1:
                return False
        return True

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        entities = context.scene.sketcher.entities.selected_entities

        c = context.scene.sketcher.constraints.new_from_type(self.type)

        args = []
        # fill in entities!
        for prop in ("entity1", "entity2", "entity3", "entity4"):
            if hasattr(c, prop):
                arg = getattr(self, prop)
                setattr(c, prop, arg)
                args.append(arg)

        if not self.initialized and hasattr(c, "init_props"):
            # TODO: Don't overwrite props if not neccesary
            value, setting = c.init_props(args)
            if value is not None:
                self.value = value
            if setting is not None:
                self.setting = setting
        self.initialized = True

        sketch = None
        if context.scene.sketcher.active_sketch_i:
            sketch = context.scene.sketcher.active_sketch

        if sketch and c.needs_wp() != WpReq.FREE:
            c.sketch = sketch

        if hasattr(c, "value"):
            c.value = self.value
        if hasattr(c, "setting"):
            c.setting = self.setting

        logger.debug("Add: {}".format(c))
        self.target = c
        solve_system(context)
        refresh(context)
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        c = self.target
        if not c:
            return

        if hasattr(c, "value"):
            layout.prop(self, "value", text=c.rna_type.properties["value"].name)
        if hasattr(c, "setting"):
            layout.prop(self, "setting", text=c.rna_type.properties["setting"].name)


class_defines.slvs_entity_pointer(
    VIEW3D_OT_slvs_add_constraint, "entity1", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    VIEW3D_OT_slvs_add_constraint, "entity2", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    VIEW3D_OT_slvs_add_constraint, "entity3", options={"SKIP_SAVE"}
)
class_defines.slvs_entity_pointer(
    VIEW3D_OT_slvs_add_constraint, "entity4", options={"SKIP_SAVE"}
)


class View3D_OT_slvs_delete_constraint(Operator):
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
    def description(CLS, context, properties):
        if properties.type:
            return "Delete: " + properties.type
        return ""

    def execute(self, context):
        constraints = context.scene.sketcher.constraints

        # NOTE: It's not really neccesary to first get the
        # constraint from it's index before deleting

        constr = constraints.get_from_type_index(self.type, self.index)
        logger.debug("Delete: {}".format(constr))

        constraints.remove(constr)

        solve_system(context)
        refresh(context)
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
        type, index = self.type, self.index
        constraints = context.scene.sketcher.constraints
        constr = constraints.get_from_type_index(type, index)

        def draw_func(self, context):
            layout = self.layout
            name = constr.rna_type.properties["value"].name
            layout.prop(constr, "value", text=name)

            if hasattr(constr, "setting"):
                layout.prop(constr, "setting")

            layout.separator()
            props = layout.operator(View3D_OT_slvs_delete_constraint.bl_idname)
            props.type = type
            props.index = index

        context.window_manager.popup_menu(
            draw_func,
            title="Tweak Constraint: " + constr.rna_type.properties["value"].name,
        )

        return {"FINISHED"}


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
            sketch.target_mesh = sketch.target_curve_object.to_mesh().copy()

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
    View3D_OT_invoke_tool,
    View3D_OT_slvs_set_active_sketch,
    View3D_OT_slvs_delete_entity,
    VIEW3D_OT_slvs_add_constraint,
    View3D_OT_slvs_solve,
    View3D_OT_slvs_delete_constraint,
    View3D_OT_slvs_tweak_constraint_value_pos,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
