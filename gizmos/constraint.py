import math

import blf
import gpu
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from .. import icon_manager, units
from ..declarations import Gizmos, GizmoGroups, Operators
from ..utilities.preferences import get_prefs
from ..utilities.view import get_2d_coords
from .base import ConstraintGizmo
from .utilities import Color, get_color, set_gizmo_colors
from ..utilities.view import get_scale_from_pos

GIZMO_OFFSET = Vector((1.0, 1.0))
FONT_ID = 0


def _get_formatted_value(context, constr):
    unit = constr.rna_type.properties["value"].unit
    value = constr.value

    if unit == "LENGTH":
        if constr.type == "DIAMETER" and constr.setting:
            s = "R" + units.format_distance(value)
        else:
            s = units.format_distance(value)
        return s
    elif unit == "ROTATION":
        return units.format_angle(value)
    return ""


class VIEW3D_GGT_slvs_constraint(GizmoGroup):
    bl_idname = GizmoGroups.Constraint
    bl_label = "Constraint Gizmo Group"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True

    def setup(self, context):
        from ..model.sketch_ref import get_active_sketch
        active_sketch = get_active_sketch(context)

        # Build mapping: placement_key → [constraints]
        # Uses curve_ids when available, falls back to entity objects
        mapping = {}
        if not active_sketch:
            return
        for c in active_sketch.constraints.all:

            # Try curve_id placements first
            cid_placements = c.curve_id_placements()
            if cid_placements:
                for cid in cid_placements:
                    key = ("curve_id", cid)
                    mapping.setdefault(key, []).append(c)
            elif hasattr(c, "placements"):
                # Fallback to entity placements
                for e in c.placements():
                    if e and hasattr(e, "placement") and e.is_visible(context):
                        key = ("entity", e.slvs_index)
                        mapping.setdefault(key, []).append(c)

        for key, constrs in mapping.items():
            kind, ident = key

            for i, c in enumerate(constrs):
                gz = self.gizmos.new(VIEW3D_GT_slvs_constraint.bl_idname)
                gz.type = c.type
                gz.index = active_sketch.constraints.get_index(c)

                if kind == "curve_id":
                    gz.entity_index = -1
                    gz.curve_id = ident
                else:
                    gz.entity_index = ident
                    gz.curve_id = getattr(c, 'curve_id_1', "")

                ui_scale = context.preferences.system.ui_scale
                scale = get_prefs().gizmo_scale * ui_scale
                offset_base = Vector((scale * 1.0, 0.0))
                offset = offset_base * i * ui_scale

                gz.offset = offset
                gz.scale_basis = scale

                set_gizmo_colors(gz, c)

                gz.use_draw_modal = True

                op = Operators.ContextMenu
                props = gz.target_set_operator(op)
                props.type = c.type
                props.index = gz.index

                props.highlight_hover = True
                props.highlight_members = True

        # Add value gizmos for dimensional constraints
        for c in active_sketch.constraints.dimensional:
            gz = self.gizmos.new(VIEW3D_GT_slvs_constraint_value.bl_idname)
            index = active_sketch.constraints.get_index(c)
            gz.type = c.type
            gz.index = index

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = c.type
            props.index = index

    def refresh(self, context):
        # recreate gizmos here!
        self.gizmos.clear()
        self.setup(context)


class VIEW3D_GT_slvs_constraint(ConstraintGizmo, Gizmo):
    bl_idname = Gizmos.Constraint

    __slots__ = (
        "custom_shape",
        "type",
        "index",
        "entity_index",
        "offset",
    )

    def _update_matrix_basis(self, context, constr):
        pos = None
        if hasattr(self, "curve_id") and self.curve_id:
            from ..model.sketch_ref import get_active_sketch
            sketch = get_active_sketch(context)
            if sketch:
                from ..utilities.curve_data import get_curve_placement
                world_pos = get_curve_placement(sketch, self.curve_id)
            else:
                return

            if world_pos is None:
                return
            pos = get_2d_coords(context, world_pos)
            if not pos:
                return

            scale_3d = max(1, get_scale_from_pos(pos, context.region_data) / 500)
            pos += GIZMO_OFFSET * self.scale_basis / scale_3d + self.offset

        if pos:
            mat = Matrix.Translation(Vector((pos[0], pos[1], 0.0)))
            self.matrix_basis = mat

    def test_select(self, context, location):
        if not context.scene.sketcher.selectable_constraints:
            return -1

        location = Vector(location).to_3d()
        location -= self.matrix_basis.translation
        location *= 1.0 / self.scale_basis

        if math.pow(location.length, 2) < 1.0:
            return 0
        return -1

    def draw(self, context):
        constraint = self._get_constraint(context)
        if not constraint.visible:
            return
        col = self._set_colors(context, constraint)
        self._update_matrix_basis(context, constraint)

        with gpu.matrix.push_pop():
            gpu.matrix.load_matrix(self.matrix_basis)
            scale = self.scale_basis
            gpu.matrix.scale(Vector((scale, scale)))
            icon_manager.draw(self.type, col)

    def setup(self):
        pass


class VIEW3D_GT_slvs_constraint_value(ConstraintGizmo, Gizmo):
    """Display the value of a dimensional constraint"""

    bl_idname = Gizmos.ConstraintValue

    __slots__ = ("type", "index", "width", "height")

    def test_select(self, context, location):
        if not context.scene.sketcher.selectable_constraints:
            return -1

        coords = Vector(location) - self.matrix_basis.translation.to_2d()

        width, height = self.width, self.height
        if -width / 2 < coords.x < width / 2 and -height / 2 < coords.y < height / 2:
            return 0
        return -1

    def draw(self, context):
        constr = self._get_constraint(context)

        if not constr.visible or not hasattr(constr, "value_placement"):
            return

        color = get_color(Color.Text, self.is_highlight)
        text = _get_formatted_value(context, constr)
        text_size = get_prefs().text_size

        blf.color(FONT_ID, *color)
        blf.size(FONT_ID, text_size)
        self.width, self.height = blf.dimensions(FONT_ID, text)

        margin = text_size / 4

        pos = constr.value_placement(context)
        if not pos:
            return
        self.matrix_basis = Matrix.Translation(
            pos.to_3d()
        )  # Update Matrix for selection

        blf.position(FONT_ID, pos[0] - self.width / 2, pos[1] + margin, 0)
        blf.draw(FONT_ID, text)

    def setup(self):
        self.width = 0
        self.height = 0
