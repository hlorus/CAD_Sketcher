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
CUTTER = "CUTTER"  # a solid that is cutting: hidden, or shown as a wireframe
SKETCH = "SKETCH"  # a sketch's own curves
BODY = "BODY"  # a solid that cuts nothing: simply on screen or not
WHOLE_PART = "WHOLE_PART"  # a row standing for a part, not for one feature


def row_visibility(obj, cutting, whole_part=False):
    """(kind, object) the row's eye toggles, or (None, None) if it has nothing to.

    Each row's eye acts on that row's own object, which is what makes the icon
    mean one thing: a sketch row shows its curves, a feature row shows its solid,
    and a row standing for a whole part shows the part. The one special case is a
    solid that is cutting, whose visibility the display rules own.

    ``cutting`` is the set from :func:`cutting_bodies`; ``whole_part`` says the
    row stands for a part rather than for one of its features.
    """
    body, sketch = row_parts(obj)
    if whole_part:
        return (WHOLE_PART, body) if body is not None else (None, None)
    if sketch is not None and body is None:
        return SKETCH, sketch
    if body is not None:
        return (CUTTER, body) if body.name in cutting else (BODY, body)
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
    """A draw order: the base feature first, each sketch under the feature it draws.

    ``scene.objects`` is kept sorted by name, which would file the part's own
    body wherever its name happens to fall (a cut listed above the thing it cuts)
    and scatter the sketches among the solids. The base is what everything else
    was built on, so it leads; every other feature follows by name, each with its
    own sketch beneath it.

    Blender reads this as "the item at index i moves to position order[i]", so it
    has to be a permutation of every item, filtered-out ones included.
    """
    from ..utilities.body import body_of

    def key(obj):
        # Sort a sketch as its feature, one place behind it.
        feature = body_of(obj) if is_sketch_object(obj) else obj
        if feature is None:
            feature = obj
        return (feature != root, feature.name, obj is not feature)

    ranked = sorted(range(len(objects)), key=lambda i: key(objects[i]))
    order = [0] * len(objects)
    for position, index in enumerate(ranked):
        order[index] = position
    return order


def is_feature_row(obj) -> bool:
    """Whether ``obj`` earns a row of its own.

    A body, a mesh that belongs to a part without being one (imported geometry
    joined by hand), or a sketch. A sketch gets its own row under the feature it
    draws, so that each row has exactly one thing to show or hide: the feature's
    solid on one, the sketch's curves on the other.
    """
    from ..utilities.body import is_body
    from ..utilities.part import is_part_root, part_root_of

    if is_body(obj) or is_sketch_object(obj):
        return True
    return obj.type == "MESH" and (is_part_root(obj) or part_root_of(obj) is not None)


def is_sketch_row(obj) -> bool:
    """Whether this row is a sketch rather than the feature it draws."""
    return is_sketch_object(obj)


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

            from ..utilities.part import is_part_root

            body, sketch = row_parts(obj)
            scope, _root = list_scope(context)
            # Outside a part every row stands for a whole part, so its controls
            # act on the part rather than on one feature inside it.
            whole_part = scope != PART and body is not None and is_part_root(body)
            sketch_row = is_sketch_row(obj)

            row = layout.row(align=True)
            if sketch_row:
                # Nested under the feature it draws.
                row.label(text="", icon="BLANK1")

            self._draw_eye(row, obj, context, whole_part)

            # Editable name -- expands to fill, pushing the icons below to the
            # right edge of the row (standard Blender UIList layout). A sketch's
            # name is derived from its body, so typing one would be re-derived
            # away on the next update: it is shown, not offered.
            if sketch_row:
                row.label(text=obj.name)
            else:
                row.prop(body or sketch, "name", text="", emboss=False)

            # Trailing controls: solver-state, open, edit, delete
            if sketch is not None and sketch.get("solver_state", "OKAY") != "OKAY":
                state = Sketch(sketch).get_solver_state()
                row.label(text="", icon=state.icon)

            self._draw_open(row, obj, body, sketch, whole_part, sketch_row)

            self._draw_delete(row, body, sketch, whole_part, sketch_row)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon="OUTLINER_OB_MESH")

    @staticmethod
    def _draw_eye(row, obj, context, whole_part) -> None:
        """The one control that says whether this row's thing is on screen."""
        kind, target = row_visibility(obj, cutting_now(context.scene), whole_part)

        if kind == WHOLE_PART:
            # The row is a part, so the eye is the part's, exactly as in the
            # header above the list.
            row.operator(
                Operators.SetPartVisibility,
                text="",
                icon="HIDE_ON" if target.hide_get() else "HIDE_OFF",
                emboss=False,
            ).part_name = target.name
        elif kind == CUTTER:
            # A cutter is hidden while it cuts, so its solid has no other control
            # anywhere: without this the body looks deleted. Shown as a wireframe,
            # which is what there is to show once its volume has been merged into
            # the result.
            row.operator(
                Operators.SetCutterVisibility,
                text="",
                icon="HIDE_ON" if target.hide_viewport else "HIDE_OFF",
                emboss=False,
            ).body_name = target.name
        elif kind == BODY:
            row.operator(
                Operators.SetBodyVisibility,
                text="",
                icon="HIDE_ON" if target.hide_get() else "HIDE_OFF",
                emboss=False,
            ).body_name = target.name
        elif kind == SKETCH:
            row.operator(
                Operators.SetSketchVisibility,
                text="",
                icon="HIDE_ON" if target.hide_viewport else "HIDE_OFF",
                emboss=False,
            ).sketch_name = target.name
        else:
            row.label(text="", icon="MESH_DATA")

    @staticmethod
    def _draw_open(row, obj, body, sketch, whole_part, sketch_row) -> None:
        """Open what the row is: a part, a sketch, a mesh, or a feature's inputs."""
        if whole_part:
            # A part holds many sketches, so there is nothing single to open: it
            # opens the part, and the list descends into its features.
            row.operator(
                Operators.OpenPart, text="", icon="DISCLOSURE_TRI_RIGHT", emboss=False
            ).part_name = body.name
            return

        if sketch_row:
            row.operator(
                Operators.SetActiveSketch,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            ).sketch_name = obj.name
            return

        if body is not None:
            # The feature's own row opens what it was made with. A mesh nobody
            # drew has no such inputs, so it opens Blender's Edit Mode instead.
            if body.modifiers:
                row.operator(
                    Operators.EditFeature, text="", icon="MODIFIER", emboss=False
                ).body_name = body.name
            elif body.type == "MESH":
                row.operator(
                    Operators.EditBodyMesh, text="", icon="EDITMODE_HLT", emboss=False
                ).body_name = body.name
            return

        spent = row.row(align=True)
        spent.enabled = False
        spent.label(text="", icon="OUTLINER_DATA_GP_LAYER")

    @staticmethod
    def _draw_delete(row, body, sketch, whole_part=False, sketch_row=False) -> None:
        """Delete the row as the thing it is: a feature, a part, or a sketch."""
        from ..operators.delete_part import feature_root
        from ..utilities.part import is_part_root

        if sketch_row and body is None and sketch is not None:
            # A sketch that draws a feature goes with the feature, whose own row
            # carries that; one belonging to nothing is deleted on its own.
            from ..utilities.body import body_of

            if body_of(sketch) is not None:
                spent = row.row(align=True)
                spent.enabled = False
                spent.label(text="", icon="X")
                return
            row.operator(
                Operators.DeleteSketch, text="", icon="X", emboss=False
            ).sketch_name = sketch.name
            return

        if body is not None and not whole_part and feature_root(body) is not None:
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
