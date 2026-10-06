import gpu
from bpy import app
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .. import global_data
from ..declarations import Operators
from ..drawing import frame_cache, selection
from ..model.types import GenericConstraint
from ..shaders import Shaders
from .utilities import (
    dimension_line_widths,
    get_constraint_color_type,
    set_gizmo_colors,
)


def use_plain_attributes(cls) -> None:
    """Skip ``Gizmo``'s per-attribute property lookup on a gizmo class.

    ``bpy.types.Gizmo`` routes every attribute access through a lookup of the
    gizmo type's registered properties first, costing a path resolve per access.
    Constraint gizmos register no such properties but read a dozen attributes
    for each of hundreds of gizmos every redraw, so they use plain access.
    """
    import bpy

    cls.__getattribute__ = bpy.types.bpy_struct.__getattribute__
    cls.__setattr__ = bpy.types.bpy_struct.__setattr__


# gizmo pointer -> the color it was last given, so it is only set when it changes.
_gizmo_colors = {}


class ConstraintGizmo:
    def _get_constraint(self, context):
        sketch = frame_cache.active_sketch(context)
        if not sketch:
            return None
        return frame_cache.constraint_at(sketch, self.type, self.index)

    def get_constraint_color(self, constraint: GenericConstraint):
        is_highlight = constraint == selection.highlight_constraint or self.is_highlight
        col = get_constraint_color_type(constraint)
        return frame_cache.constraint_color(col, is_highlight)

    def _set_colors(self, context, constraint: GenericConstraint):
        """Overwrite default color when gizmo is highlighted"""

        color_setting = self.get_constraint_color(constraint)
        color = tuple(color_setting[:3])
        pointer = self.as_pointer()
        if _gizmo_colors.get(pointer) != color:
            self.color = color
            _gizmo_colors[pointer] = color
        return color_setting


# gizmo pointer -> the matrix_basis it was last given.
_gizmo_bases = {}


def _local_to_world(matrix, coords):
    """Gizmo-local line vertices (2D or 3D) transformed by ``matrix``."""
    return [(matrix @ Vector(point).to_3d())[:] for point in coords]


def _line_batch(matrix, coords):
    """World-space ``LINES`` batch for the polyline shader, or None if empty.

    The shader expands the stroke in screen space from ``lineWidth``. That
    uniform is what actually thickens the line: ``gpu.state.line_width_set``
    has no effect on macOS, which is why these are not a gizmo ``LINES`` shape.
    """
    if len(coords) < 2:
        return None
    shader = Shaders.polyline_color_3d()
    return batch_for_shader(shader, "LINES", {"pos": _local_to_world(matrix, coords)})


def _draw_dimension_lines(context, leader_batch, witness_batch, color) -> None:
    """Draw extension lines, then the dimension line over them."""
    if leader_batch is None and witness_batch is None:
        return
    leader_width, witness_width = dimension_line_widths()
    shader = Shaders.polyline_color_3d()
    shader.bind()
    gpu.state.blend_set("ALPHA")
    shader.uniform_float("color", tuple(color))
    if app.version >= (4, 5):
        shader.uniform_float(
            "viewportSize", (context.region.width, context.region.height)
        )
    # Witness lines first: where the two meet, the heavier stroke stays visible.
    if witness_batch is not None:
        gpu.state.line_width_set(witness_width)
        if app.version >= (4, 5):
            shader.uniform_float("lineWidth", witness_width)
        witness_batch.draw(shader)
    if leader_batch is not None:
        gpu.state.line_width_set(leader_width)
        if app.version >= (4, 5):
            shader.uniform_float("lineWidth", leader_width)
        leader_batch.draw(shader)
    gpu.shader.unbind()
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def forget_gizmos() -> None:
    """Drop what was remembered per gizmo, before a group recreates its gizmos.

    A new gizmo can reuse a freed one's pointer and must not inherit its state.
    """
    _gizmo_colors.clear()
    _gizmo_bases.clear()


class ConstraintGizmoGeneric(ConstraintGizmo):
    def _update_matrix_basis(self, constr, basis=None):
        if basis is None:
            basis = constr.matrix_basis()
        pointer = self.as_pointer()
        if _gizmo_bases.get(pointer) is not basis:
            self.matrix_basis = basis
            _gizmo_bases[pointer] = basis

    def setup(self):
        pass

    def _shape_signature(self, context, constr, basis):
        """Everything the drawn shape depends on. The shape (arrows/helplines) is
        rebuilt only when this changes, so a static viewport -- including every
        redraw during a modal drag -- doesn't re-upload a GPU batch per gizmo."""
        return (
            round(getattr(constr, "value", 0.0), 7),
            round(getattr(constr, "radius", 0.0), 7),
            round(getattr(constr, "draw_offset", 0.0), 7),
            round(getattr(constr, "draw_outset", 0.0), 7),
            round(getattr(constr, "leader_angle", 0.0), 7),
            tuple(v for row in basis for v in row),
            # Helplines follow the referenced geometry, not just the placement.
            frame_cache.dimension_geometry_key(
                frame_cache.active_sketch(context), constr
            ),
            frame_cache.view_scale_key(context),
            frame_cache.arrow_scale(),
            frame_cache.ui_scale(context),
        )

    def _ensure_shape(self, context, constr):
        """Build the polyline batches and the pick shape when their inputs change.

        ``_create_shape`` returns ``(leader, witness)`` in local space. The
        leader is the dimension line and its arrowheads; the witness lines are
        the extensions. Batches are cached because rebuilding them per gizmo
        per redraw made constraint-heavy sketches laggy.
        """
        basis = frame_cache.dimension_basis(frame_cache.active_sketch(context), constr)
        self._update_matrix_basis(constr, basis)
        sig = self._shape_signature(context, constr, basis)
        if getattr(self, "_shape_sig", None) == sig:
            return
        leader, witness = self._create_shape(context, constr)
        self._leader_batch = _line_batch(self.matrix_world, leader)
        self._witness_batch = _line_batch(self.matrix_world, witness)
        # Extension lines stay out of the pick shape so a click where they meet
        # the geometry still reaches that geometry.
        self.custom_shape = (
            self.new_custom_shape("LINES", leader) if len(leader) >= 2 else None
        )
        self._shape_sig = sig

    def draw(self, context):
        constr = self._get_constraint(context)
        if not constr or not constr.visible:
            return
        color = self._set_colors(context, constr)
        self._ensure_shape(context, constr)
        _draw_dimension_lines(
            context,
            getattr(self, "_leader_batch", None),
            getattr(self, "_witness_batch", None),
            color,
        )

    def draw_select(self, context, select_id):
        # While a stateful operator runs, stay out of the gizmo select buffer so
        # the dimension label (which follows the cursor) neither highlights nor
        # swallows a click meant for the geometry underneath -- gating the select
        # pass directly avoids the one-frame lag/flicker of toggling hide_select.
        if global_data.stateful_op_running:
            return
        constr = self._get_constraint(context)
        if not constr or not constr.visible:
            return
        self._ensure_shape(context, constr)
        shape = getattr(self, "custom_shape", None)
        if shape is None:
            return
        self.draw_custom_shape(shape, select_id=select_id)


# gizmo group pointer -> signature of the constraints its gizmos were made for.
_group_signatures = {}


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D", "SHOW_MODAL_ALL"}

    def setup(self, context):
        from ..model.sketch_ref import get_active_sketch

        forget_gizmos()
        _group_signatures[self.as_pointer()] = self._signature(context)
        active_sketch = get_active_sketch(context)
        if not active_sketch:
            return
        for index, c in enumerate(active_sketch.constraints.get_list(self.type)):
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = index

            set_gizmo_colors(gz, c)

            gz.use_draw_modal = True
            gz.target_set_prop("offset", c, "draw_offset")

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = self.type
            props.index = gz.index

    def refresh(self, context):
        """Recreate the gizmos only when this type's constraints changed.

        Blender refreshes groups on nearly every update. Each gizmo binds its
        offset to its constraint, so the gizmos are recreated whenever a
        constraint was added, removed or moved in memory (adding one can move the
        others), and otherwise kept.
        """
        if _group_signatures.get(self.as_pointer()) == self._signature(context):
            return
        self.gizmos.clear()
        self.setup(context)

    def _signature(self, context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return None
        return (
            sketch.target_object.as_pointer(),
            tuple(c.as_pointer() for c in sketch.constraints.get_list(self.type)),
        )

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True
