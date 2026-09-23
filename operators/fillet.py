"""The ``Fillet`` tool: pick the edges the ``CAD Sketcher Fillet`` modifier rounds.

A stateful tool like the other node tools: each click picks one
edge of the object's output and rounds it (clicking a rounded edge again drops
it), so every pick is its own step. While the tool is active the object shows
without its fillet, so a click lands on the element the node tree indexes. The
picks are stored on the modifier as element indices, so nothing has to be
expressed as a rule.
"""

import bpy
from bpy.props import FloatProperty, StringProperty
from bpy.types import Context, Event, MeshEdge, Operator

from ..declarations import Operators
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.geometry import evaluated_surface_mesh
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.fillet_nodes import (
    FILLET_NODE_GROUP,
    build_fillet_node_group,
    fillet_input_ids,
    get_domain,
    get_picks,
    set_picks,
)
from .base_3d import Operator3d
from .modifiers import set_modifier_input

# Fillets hidden while the tool picks, as ``{(object, modifier): True}``. The tool
# shows the geometry the fillet reads (like edit mode shows base geometry), so the
# element a click lands on is the one the node tree indexes.
_hidden = {}


def fillet_target(ob):
    """The object a fillet belongs on: a sketch is source, its body carries the
    stack (see utilities/body), so redirect to that."""
    from ..utilities.body import body_of

    if ob is None:
        return None
    return body_of(ob) or ob


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


def picked_edge_points(context: Context, ob, picks, domain: str) -> list:
    """World endpoints of the picked edges, for drawing them."""
    points = []
    if domain != "EDGE" or not picks:
        return points
    with evaluated_surface_mesh(context, ob) as (mesh, matrix):
        if mesh is None:
            return points
        for index in picks:
            if 0 <= index < len(mesh.edges):
                points.extend(
                    matrix @ mesh.vertices[v].co for v in mesh.edges[index].vertices
                )
    return points


def hide_fillet(context: Context, ob) -> None:
    """Show ``ob`` without its fillet, and remember to put it back."""
    modifier = fillet_modifier(ob)
    if modifier is None or not modifier.show_viewport:
        return
    modifier.show_viewport = False
    _hidden[(ob.name, modifier.name)] = True
    ob.update_tag()
    context.view_layer.update()


def restore_fillets(context: Context) -> None:
    """Undo :func:`hide_fillet` for every object it touched."""
    for ob_name, mod_name in list(_hidden):
        ob = bpy.data.objects.get(ob_name)
        modifier = ob.modifiers.get(mod_name) if ob else None
        if modifier is not None:
            modifier.show_viewport = True
            ob.update_tag()
    _hidden.clear()
    if context.view_layer:
        context.view_layer.update()


def fillet_tool_active(context: Context) -> bool:
    """Whether the Fillet workspace tool is the active tool."""
    from ..declarations import WorkSpaceTools

    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return False
    try:
        tool = workspace.tools.from_space_view3d_mode(context.mode)
    except Exception:
        return False
    return tool is not None and tool.idname == WorkSpaceTools.Fillet


def sync_fillet_visibility(context: Context) -> None:
    """Hide the fillet exactly while its tool is active, else show it again.

    The picking session lasts as long as the tool: the object shows the geometry
    the fillet reads (so a click lands on the element the node tree indexes), and
    picking up any other tool brings the rounded result back. Blender has no
    tool-activated callback, so a timer keeps the two in step; this also repairs
    the hidden state an undo step recorded mid-session.
    """
    if fillet_tool_active(context):
        ob = fillet_target(getattr(context, "object", None))
        if ob is not None:
            hide_fillet(context, ob)
    elif _hidden:
        restore_fillets(context)


_TIMER_INTERVAL = 0.2


def _sync_timer():
    sync_fillet_visibility(bpy.context)
    return _TIMER_INTERVAL


class View3D_OT_slvs_fillet_select(Operator, Operator3d):
    """Click the edges to round; click a rounded edge again to drop it"""

    bl_idname = Operators.FilletSelect
    bl_label = "Fillet"
    bl_options = {"REGISTER", "UNDO"}

    amount: FloatProperty(
        name="Amount",
        description="Fillet width",
        default=0.1,
        min=0.0,
        subtype="DISTANCE",
    )
    # One invocation keeps picking: every click rounds another edge, and the run
    # ends with Esc/right-click like the other tools.
    repeat_states = True
    # Set while the redo panel re-runs the operator: a pick is then re-applied
    # rather than toggled, so adjusting Amount doesn't undo the pick itself.
    _redoing = False
    # Object whose fillet is being edited, so a redo re-finds the modifier.
    target_name: StringProperty(options={"HIDDEN"})

    states = (
        state_from_args(
            "Edge",
            description="Click an edge of the object's output to round it",
            pointer="edge",
            types=(MeshEdge,),
            use_create=False,
        ),
    )

    def state_property(self, state_index):
        # A native MeshEdge pointer has no editable fallback property (as for the
        # node tools): don't advertise the placeholder the entity base returns.
        return None

    def execute(self, context: Context):
        self._redoing = True
        return super().execute(context)

    def init(self, context: Context, event: Event):
        build_fillet_node_group()
        return True

    def _picked(self):
        """``(object, edge index)`` of the current pick, or ``(None, -1)``.

        A native MeshEdge pointer is stored as ``(object name, index)`` -- the
        same shape the revolve axis reads back.
        """
        try:
            name, index = self.get_state_pointer(index=0, implicit=True)
        except Exception:
            return None, -1
        ob = bpy.data.objects.get(name) if name else None
        return ob, int(index)

    def _target(self, context: Context):
        ob, _index = self._picked()
        if ob is None:
            ob = bpy.data.objects.get(self.target_name) or context.object
        return fillet_target(ob)

    def main(self, context: Context):
        ob, index = self._picked()
        ob = fillet_target(ob)
        if ob is None or index < 0:
            return False
        self.target_name = ob.name

        modifier = fillet_modifier(ob)
        if modifier is None:
            modifier = add_fillet_modifier(ob, self.amount)
        else:
            set_modifier_input(
                modifier, fillet_input_ids(modifier.node_group)["Amount"], self.amount
            )

        picks = get_picks(modifier)
        if index in picks and not self._redoing:
            picks.remove(index)
        elif index not in picks:
            picks.append(index)
        if picks:
            set_picks(modifier, picks, get_domain(modifier))
        else:
            # Nothing left to round, and an empty pick set would round everything.
            ob.modifiers.remove(modifier)
        # Keep showing the pre-fillet geometry: the session lasts as long as the
        # tool, so the next click picks on the same elements.
        sync_fillet_visibility(context)
        return True

    def draw_settings(self, context: Context):
        self.layout.prop(self, "amount")


_register_classes, _unregister_classes = register_stateops_factory(
    (View3D_OT_slvs_fillet_select,)
)


def register():
    _register_classes()
    if not bpy.app.background and not bpy.app.timers.is_registered(_sync_timer):
        bpy.app.timers.register(_sync_timer, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_sync_timer):
        bpy.app.timers.unregister(_sync_timer)
    restore_fillets(bpy.context)
    _unregister_classes()
