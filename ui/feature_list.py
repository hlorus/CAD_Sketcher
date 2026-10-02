"""The feature list: what the part in focus is made of.

Rows are *bodies*, not sketches. A body is the stable object -- it carries the
feature stack, it is what a part is rooted in, and the sketch's name is derived
from it -- so a feature with no sketch at all (imported geometry made a part by
hand) is listed, and a sketch is reached through the body it realises.

What the list holds depends on what is in focus (see :func:`list_scope`): one
part's features, one assembly's parts, or every part in the file.
"""

import bpy
from bpy.types import Context, PropertyGroup, UILayout, UIList

from ..declarations import Operators
from ..model.sketch_ref import Sketch, is_sketch_object

# The cutting set for the draw in progress, keyed by scene name. Blender builds a
# *different* UIList instance for ``filter_items`` and for ``draw_item``, so
# anything stashed on ``self`` in one is gone in the other -- which is why the
# cutting rows never showed what they were. Held here instead, refreshed by
# ``filter_items``, which runs first in every draw pass.
_cutting_cache = {}


def cutting_bodies(scene) -> set:
    """Names of the bodies currently feeding a boolean, so cutting rows say so.

    Gathered in one pass because the list needs it per row, and a per-row scan of
    every object's modifiers would run as often as the panel redraws.
    """
    from ..operators.modifiers import boolean_cutters

    cutting = set()
    for body in scene.objects:
        for cutter in boolean_cutters(body):
            cutting.add(cutter.name)
    return cutting


def cutting_now(scene) -> set:
    """What ``draw_item`` reads: the set the last filter pass left behind.

    Computed here if a draw somehow reaches a row without filtering first, so a
    row is never told that nothing is cutting.
    """
    if scene.name not in _cutting_cache:
        _cutting_cache[scene.name] = cutting_bodies(scene)
    return _cutting_cache[scene.name]


def row_parts(obj):
    """(body, sketch) for a row: what it is built from, and what drew it.

    Rows are bodies -- the body is what a part is built from, what carries the
    features, and what the name belongs to -- but either half can be missing. A
    mesh joined to a part by hand was never drawn, so it has no sketch; a file
    from before every sketch got a body holds a sketch with no body.
    """
    from ..utilities.body import is_body, sketch_of

    if is_body(obj):
        return obj, sketch_of(obj)
    if is_sketch_object(obj):
        return None, obj
    return obj, None


# What a row's eye acts on.
CUTTER = "CUTTER"
SKETCH = "SKETCH"


def row_visibility(obj, cutting):
    """(kind, object) the row's eye toggles, or (None, None) if it has nothing to.

    One slot, because the two meanings never apply at once: a body that is
    cutting is hidden by the display rules, so its solid is the thing to show or
    hide; any other row has only its profile to offer. ``cutting`` is the set
    from :func:`cutting_bodies`.
    """
    body, sketch = row_parts(obj)
    # The cutter is the body, or the sketch itself in a file from before bodies
    # existed, which carried the stack on the sketch.
    cutter = body or sketch
    if cutter is not None and cutter.name in cutting:
        return CUTTER, cutter
    if sketch is not None:
        return SKETCH, sketch
    return None, None


# What the list is showing.
PART = "PART"
ASSEMBLY = "ASSEMBLY"
GLOBAL = "GLOBAL"


def list_scope(context):
    """(scope, root) the list is showing: one part, one assembly, or the file.

    Read from the *active* object rather than the selection, which is what
    ``focused_part`` does for the workplane picker. Two reasons the list wants the
    other rule: hiding a part deselects it, so a selection-based list would drop
    the part at the moment you hid it and take the control that unhides it with
    it; and a list that empties every time you click beside your work is more
    startling than useful.

    Through the view layer, not ``context.active_object``, which is context state
    and goes to None as soon as the object is hidden -- the very case this is here
    for. The view layer keeps the pointer.

    A part is the narrowest answer and wins, so the active object inside an
    assembly lists its part rather than the assembly's other parts. With neither
    the list falls back to the file: every part in it, plus anything not in one.
    """
    from ..utilities.part import assembly_root_of, part_root_of

    obj = context.view_layer.objects.active
    root = part_root_of(obj)
    if root is not None:
        return PART, root

    assembly = assembly_root_of(obj)
    if assembly is not None:
        return ASSEMBLY, assembly

    return GLOBAL, None


def in_scope(obj, scope, root) -> bool:
    """Whether ``obj`` belongs in the list as it is currently scoped.

    A part lists what it is made of, base feature first. The wider scopes list
    *parts* rather than their insides, since a file's worth of features
    interleaved by name says nothing about what belongs to what.
    """
    from ..utilities.part import assembly_root_of, is_part_root, part_root_of

    if scope == PART:
        # The root included: it is the base feature, the one the part was built
        # from, and it leads the list (see ``base_first``).
        return part_root_of(obj) == root

    if scope == ASSEMBLY:
        return is_part_root(obj) and assembly_root_of(obj) == root

    # Global: every part, and anything loose that has not joined one yet.
    return is_part_root(obj) or part_root_of(obj) is None


def base_first(objects, root):
    """A draw order putting the part's base feature at the top.

    ``scene.objects`` is kept sorted by name, which would file the part's own
    body wherever its name happens to fall -- a cut listed above the thing it
    cuts. The base is what everything else was built on, so it leads and the rest
    keep their names' order behind it.

    Blender reads this as "the item at index i moves to position order[i]", so it
    has to be a permutation of every item, filtered-out ones included.
    """
    ranked = sorted(
        range(len(objects)),
        key=lambda i: (objects[i] != root, objects[i].name),
    )
    order = [0] * len(objects)
    for position, index in enumerate(ranked):
        order[index] = position
    return order


def is_feature_row(obj) -> bool:
    """Whether ``obj`` earns a row of its own.

    A body, a mesh that belongs to a part without being one (imported geometry
    joined by hand), or a bodyless sketch from an older file. A sketch that has a
    body is listed through it, not twice.
    """
    from ..utilities.body import body_of, is_body
    from ..utilities.part import is_part_root, part_root_of

    if is_body(obj):
        return True
    if is_sketch_object(obj):
        return body_of(obj) is None
    return obj.type == "MESH" and (is_part_root(obj) or part_root_of(obj) is not None)


class VIEW3D_UL_features(UIList):
    """One row per feature of whatever is in focus.

    Bound to ``scene.objects`` and filtered down in ``filter_items`` -- no
    separate backing collection is required. Each row lets you toggle what is
    shown, open what the row is made of, rename it and delete it.
    """

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: int,
        active_data: PropertyGroup,
        active_propname: str,
        index: int = 0,
    ):
        obj = item

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if not obj:
                layout.label(text="", translate=False, icon="OUTLINER_OB_MESH")
                return

            body, sketch = row_parts(obj)
            row = layout.row(align=True)

            kind, target = row_visibility(obj, cutting_now(context.scene))
            if kind == CUTTER:
                # A cutter is hidden while it cuts, so its solid has no other
                # control anywhere: without this the body looks deleted. Shown as
                # a wireframe, which is what there is to show once its volume has
                # been merged into the result.
                row.operator(
                    Operators.SetCutterVisibility,
                    text="",
                    icon="HIDE_ON" if target.hide_viewport else "HIDE_OFF",
                    emboss=False,
                ).body_name = target.name
            elif kind == SKETCH:
                # Nothing is cutting here, so the eye means the profile: the
                # sketch's own curves, hidden from the moment it is created.
                row.operator(
                    Operators.SetSketchVisibility,
                    text="",
                    icon="HIDE_ON" if target.hide_viewport else "HIDE_OFF",
                    emboss=False,
                ).sketch_name = target.name
            else:
                # An imported mesh made a part by hand: no profile, and nothing
                # hiding it, so there is nothing for the eye to say.
                row.label(text="", icon="MESH_DATA")

            # Editable name -- expands to fill, pushing the icons below to the
            # right edge of the row (standard Blender UIList layout). The body's
            # name, since the sketch's is derived from it: typing one here would
            # be re-derived away on the next update.
            row.prop(body or sketch, "name", text="", emboss=False)

            # Trailing controls: solver-state, enter (edit), delete
            if sketch is not None and sketch.get("solver_state", "OKAY") != "OKAY":
                state = Sketch(sketch).get_solver_state()
                row.label(text="", icon=state.icon)

            # Enter what the row actually is. A row standing for a whole part
            # (every row but the ones of the part in focus) holds many sketches,
            # so there is nothing single to open: it opens the part instead, and
            # the list descends into its features. The icon says which.
            from ..utilities.part import is_part_root

            scope, _root = list_scope(context)
            if scope != PART and body is not None and is_part_root(body):
                row.operator(
                    Operators.OpenPart,
                    text="",
                    icon="DISCLOSURE_TRI_RIGHT",
                    emboss=False,
                ).part_name = body.name
            elif sketch is not None:
                row.operator(
                    Operators.SetActiveSketch,
                    text="",
                    icon="OUTLINER_DATA_GP_LAYER",
                    emboss=False,
                ).sketch_name = sketch.name
            elif body is not None and body.type == "MESH":
                row.operator(
                    Operators.EditBodyMesh,
                    text="",
                    icon="EDITMODE_HLT",
                    emboss=False,
                ).body_name = body.name
            else:
                spent = row.row(align=True)
                spent.enabled = False
                spent.label(text="", icon="OUTLINER_DATA_GP_LAYER")

            self._draw_delete(row, body, sketch)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon="OUTLINER_OB_MESH")

    @staticmethod
    def _draw_delete(row, body, sketch) -> None:
        """Delete the row as the thing it is: a feature, a part, or a sketch."""
        from ..operators.delete_part import feature_root
        from ..utilities.part import is_part_root

        if body is not None and feature_root(body) is not None:
            row.operator(
                Operators.DeleteFeature, text="", icon="X", emboss=False
            ).feature_name = body.name
            return
        if body is not None and is_part_root(body):
            # The base cannot go on its own -- the part is built on it, and
            # removing it would only hand the part to whatever was left -- so the
            # part goes with it. Same reach as the header's menu, which is where
            # this also lives.
            row.operator(
                Operators.DeletePart, text="", icon="X", emboss=False
            ).part_name = body.name
            return
        if sketch is not None:
            row.operator(
                Operators.DeleteSketch, text="", icon="X", emboss=False
            ).sketch_name = sketch.name

    def filter_items(self, context: Context, data, propname):
        """Show the bodies worth listing; honor the built-in name search box.

        Scoped to the part in focus when there is one, so the list says which
        part you are looking at instead of pooling every body in the file. With
        nothing in focus it lists them all, which is the old behaviour and the
        right one for a scene that has no parts yet.

        Runs once per draw, so it is also where the row-level lookups are
        gathered (which bodies are currently cutting something).
        """
        objects = getattr(data, propname)
        helper = bpy.types.UI_UL_list

        if self.filter_name:
            flags = helper.filter_items_by_name(
                self.filter_name, self.bitflag_filter_item, objects, "name"
            )
        else:
            flags = [self.bitflag_filter_item] * len(objects)

        _cutting_cache[context.scene.name] = cutting_bodies(context.scene)
        scope, root = list_scope(context)

        for i, obj in enumerate(objects):
            if not (is_feature_row(obj) and in_scope(obj, scope, root)):
                flags[i] &= ~self.bitflag_filter_item

        return flags, base_first(objects, root) if scope == PART else []
