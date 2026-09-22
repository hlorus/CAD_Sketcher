"""Operators: add the ``CAD Sketcher Fillet`` modifier and pick what it rounds.

``Add Fillet`` puts the modifier on the active object. ``Fillet Select`` is the
interactive part: hover an edge (or a corner on a flat profile) of the object's
generated geometry and click to add or remove it from what the fillet rounds. The
picked elements are stored on the modifier as indices, so nothing has to be
expressed as a rule.
"""

import gpu
from bpy.props import FloatProperty, StringProperty
from bpy.types import Context, Event, Operator, SpaceView3D
from bpy.utils import register_classes_factory
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..declarations import Operators
from ..utilities.fillet_nodes import (
    FILLET_NODE_GROUP,
    build_fillet_node_group,
    fillet_input_ids,
    get_domain,
    get_picks,
    set_picks,
)
from ..utilities.mesh_pick import element_points, element_under_cursor, generated_mesh
from .modifiers import set_modifier_input

_PICKED_COLOR = (1.0, 0.6, 0.15, 1.0)
_HOVER_COLOR = (1.0, 1.0, 1.0, 1.0)


def fillet_modifier(ob, name: str = ""):
    """The object's fillet modifier (by name, else the first one), or None."""
    for modifier in ob.modifiers:
        if modifier.type != "NODES" or modifier.node_group is None:
            continue
        if name and modifier.name != name:
            continue
        if modifier.node_group.name.startswith(FILLET_NODE_GROUP):
            return modifier
    return None


def add_fillet_modifier(ob, amount: float = 0.1):
    """Add a fillet modifier to ``ob`` and return it."""
    modifier = ob.modifiers.new("CAD Sketcher Fillet", "NODES")
    group = build_fillet_node_group()
    modifier.node_group = group
    set_modifier_input(modifier, fillet_input_ids(group)["Amount"], amount)
    return modifier


class View3D_OT_slvs_add_fillet(Operator):
    """Round the corners of the active object's output with a Fillet modifier"""

    bl_idname = Operators.AddFillet
    bl_label = "Add Fillet"
    bl_options = {"REGISTER", "UNDO"}

    amount: FloatProperty(
        name="Amount",
        description="Fillet width",
        default=0.1,
        min=0.0,
        subtype="DISTANCE",
    )

    @classmethod
    def poll(cls, context: Context) -> bool:
        ob = context.object
        return ob is not None and ob.type in {"MESH", "CURVES", "CURVE"}

    def execute(self, context: Context):
        add_fillet_modifier(context.object, self.amount)
        return {"FINISHED"}


class View3D_OT_slvs_fillet_select(Operator):
    """Click the edges (or corners) the fillet rounds"""

    bl_idname = Operators.FilletSelect
    bl_label = "Fillet Select"
    bl_options = {"REGISTER", "UNDO"}

    modifier_name: StringProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context: Context) -> bool:
        ob = context.object
        return ob is not None and ob.type in {"MESH", "CURVES", "CURVE"}

    def invoke(self, context: Context, event: Event):
        ob = context.object
        self._object = ob
        modifier = fillet_modifier(ob, self.modifier_name)
        self._created = modifier is None
        if modifier is None:
            modifier = add_fillet_modifier(ob)
        self._modifier = modifier
        self._picks = get_picks(modifier)
        self._domain = get_domain(modifier)
        self._hover = None
        # Pick on the geometry the fillet reads, not on its own rounded result:
        # the element indices must be the ones the node tree sees.
        self._was_visible = modifier.show_viewport
        modifier.show_viewport = False

        # The click that started the tool is the first pick, so no click is lost.
        self._toggle_under_cursor(context, event)

        self._handle = SpaceView3D.draw_handler_add(
            self._draw, (context,), "WINDOW", "POST_VIEW"
        )
        context.workspace.status_text_set(
            "Click elements to fillet, Enter to confirm, Esc to cancel"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _toggle_under_cursor(self, context: Context, event: Event) -> bool:
        """Add or remove the element under the cursor; True when one was hit."""
        coords = Vector((event.mouse_region_x, event.mouse_region_y))
        found = element_under_cursor(context, coords, self._domain, self._object)
        if found is None:
            return False
        index = found[0]
        if index in self._picks:
            self._picks.remove(index)
        else:
            self._picks.append(index)
        self._hover = index
        if context.area:
            context.area.tag_redraw()
        return True

    def modal(self, context: Context, event: Event):
        if event.type == "MOUSEMOVE":
            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            found = element_under_cursor(context, coords, self._domain, self._object)
            hover = found[0] if found else None
            if hover != self._hover:
                self._hover = hover
                if context.area:
                    context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            self._toggle_under_cursor(context, event)
            return {"RUNNING_MODAL"}

        if event.type in {"RET", "NUMPAD_ENTER", "SPACE"} and event.value == "PRESS":
            return self._finish(context, True)
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._finish(context, False)
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _finish(self, context: Context, apply: bool):
        SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
        self._handle = None
        self._modifier.show_viewport = self._was_visible
        context.workspace.status_text_set(None)
        if apply and self._picks:
            set_picks(self._modifier, self._picks, self._domain)
        elif self._created:
            # A modifier this run added with nothing picked would round every
            # edge; leave the object as it was instead.
            self._object.modifiers.remove(self._modifier)
        elif apply:
            set_picks(self._modifier, self._picks, self._domain)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"} if apply else {"CANCELLED"}

    def _draw(self, context: Context):
        depsgraph = context.evaluated_depsgraph_get()
        mesh, matrix = generated_mesh(depsgraph, self._object)
        if mesh is None:
            return
        gpu.state.line_width_set(3.0)
        gpu.state.depth_test_set("LESS_EQUAL")
        for indices, color in (
            (self._picks, _PICKED_COLOR),
            ([self._hover], _HOVER_COLOR),
        ):
            points = []
            for index in indices:
                if index is None:
                    continue
                element = element_points(mesh, index, self._domain, matrix)
                if len(element) == 2:
                    points.extend(element)
            if not points:
                continue
            shader = gpu.shader.from_builtin("UNIFORM_COLOR")
            batch = batch_for_shader(shader, "LINES", {"pos": points})
            shader.bind()
            shader.uniform_float("color", color)
            batch.draw(shader)
        gpu.state.line_width_set(1.0)
        gpu.state.depth_test_set("NONE")


register, unregister = register_classes_factory(
    (View3D_OT_slvs_add_fillet, View3D_OT_slvs_fillet_select)
)
