import bpy, bgl, gpu, blf
from . import functions, operators, global_data, class_defines, preferences

from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

# NOTE: idealy gizmo would expose active element as a property and
# operators would access hovered element from there
class VIEW3D_GT_slvs_preselection(Gizmo):
    bl_idname = "VIEW3D_GT_slvs_preselection"

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        # reset gizmo highlight
        if global_data.highlight_constraint:
            global_data.highlight_constraint = None
            context.area.tag_redraw()

        # ensure selection texture is up to date
        operators.ensure_selection_texture(context)

        # sample selection texture and mark hovered entitiy
        mouse_x, mouse_y = location

        buffer = bgl.Buffer(bgl.GL_FLOAT, 4)
        offscreen = global_data.offscreen
        if not offscreen:
            return -1
        with offscreen.bind():
            bgl.glReadPixels(mouse_x, mouse_y, 1, 1, bgl.GL_RGBA, bgl.GL_FLOAT, buffer)
        if buffer.to_list()[3] > 0:
            index = functions.rgb_to_index(*buffer.to_list()[:-1])
            if index != global_data.hover:
                global_data.hover = index
                context.area.tag_redraw()
        elif global_data.hover != -1:
            context.area.tag_redraw()
            global_data.hover = -1
        return -1


def context_mode_check(context, widget_group):
    tools = context.workspace.tools
    mode = context.mode
    for tool in tools:
        if (tool.widget == widget_group) and (tool.mode == mode):
            break
    else:
        context.window_manager.gizmo_group_type_unlink_delayed(widget_group)
        return False
    return True


custom_shape_verts = (
    (-1.0, -1.0),
    (1.0, -1.0),
    (-1.0, 1.0),
    (-1.0, 1.0),
    (1.0, 1.0),
    (1.0, -1.0),
)

GIZMO_OFFSET = Vector((10.0, 10.0))
GIZMO_GENERIC_SIZE = 5
GIZMO_ARROW_SCALE = 0.02

class ConstraintGizmo:
    def _get_constraint(self, context):
        return context.scene.sketcher.constraints.get_from_type_index(
            self.type, self.index
        )

    def _set_colors(self, context, constraint):
        """Overwrite default color when gizmo is highlighted"""

        theme = functions.get_prefs().theme_settings
        is_highlight = constraint == global_data.highlight_constraint
        failed = constraint.failed

        if is_highlight:
            col = theme.constraint.failed_highlight if failed else theme.constraint.highlight
        else:
            col = theme.constraint.failed if failed else theme.constraint.default

        self.color = col[:3]

class VIEW3D_GT_slvs_constraint(ConstraintGizmo, Gizmo):
    bl_idname = "VIEW3D_GT_slvs_constraint"

    __slots__ = (
        "custom_shape",
        "type",
        "index",
        "entity_index",
        "offset",
    )

    def _update_matrix_basis(self, context, constr):
        pos = None
        if hasattr(self, "entity_index"):
            entity = context.scene.sketcher.entities.get(self.entity_index)
            if not entity or not hasattr(entity, "placement"):
                return

            pos = functions.get_2d_coords(context, entity.placement())
            if not pos:
                return

            pos += GIZMO_OFFSET + self.offset

        if pos:
            mat = Matrix.Translation(Vector((pos[0], pos[1], 0.0)))
            self.matrix_basis = mat

    def test_select(self, context, location):
        location = Vector(location).to_3d()
        location -= self.matrix_basis.translation
        location *= 1.0 / self.scale_basis
        import math

        if math.pow(location.length, 2) < 1.0:
            return 0
        return -1

    def draw(self, context):
        constraint = self._get_constraint(context)
        self._set_colors(context, constraint)
        self._update_matrix_basis(context, constraint)
        self.draw_custom_shape(self.custom_shape)

    def setup(self):
        if not hasattr(self, "custom_shape"):
            self.custom_shape = self.new_custom_shape("TRIS", custom_shape_verts)


import math
from mathutils.geometry import intersect_line_plane


def _get_formatted_value(context, constr):
    units = context.scene.unit_settings
    unit = constr.rna_type.properties["value"].unit
    return bpy.utils.units.to_string(units.system, unit, constr.value)


class VIEW3D_GT_slvs_constraint_value(ConstraintGizmo, Gizmo):
    """Display the value of a dimensonal constraint"""
    bl_idname = "VIEW3D_GT_slvs_constraint_value"

    __slots__ = (
        "type",
        "index",
        "width",
        "height"
    )

    def test_select(self, context, location):
        coords = Vector(location) - self.matrix_basis.translation.to_2d()

        width, height = self.width, self.height
        if -width/2 < coords.x < width/2 and -height/2 < coords.y < height/2:
            return 0
        return -1

    def draw(self, context):
        constr = self._get_constraint(context)
        if not hasattr(constr, "value_placement"):
            return
        pos = constr.value_placement(context)

        if not pos:
            return

        # Update Matrix for selection
        self.matrix_basis = Matrix.Translation(pos.to_3d())

        text = _get_formatted_value(context, constr)
        font_id = 0

        prefs = functions.get_prefs()
        theme = prefs.theme_settings
        color = theme.constraint.text_highlight if self.is_highlight else theme.constraint.text
        blf.color(font_id, *color)

        blf.size(font_id, prefs.text_size, context.preferences.system.dpi)

        self.width, self.height = blf.dimensions(font_id, text)
        blf.position(font_id, pos[0]-self.width/2, pos[1], 0)
        blf.draw(font_id, text)

    def setup(self):
        self.width = 0
        self.height = 0


class ConstarintGizmoGeneric(ConstraintGizmo):
    def _update_matrix_basis(self, constr):
        self.matrix_basis = constr.matrix_basis()

    def setup(self):
        pass

    def draw(self, context):
        constr = self._get_constraint(context)
        self._set_colors(context, constr)
        self._update_matrix_basis(constr)

        self._create_shape(context, constr)
        self.draw_custom_shape(self.custom_shape)

    def draw_select(self, context, select_id):
        constr = self._get_constraint(context)
        self._create_shape(context, constr, select=True)
        self.draw_custom_shape(self.custom_shape, select_id=select_id)


# NOTE: Idealy the geometry batch wouldn't be recreated every redraw,
# however the geom changes with the distance value, maybe atleast track changes for that value
# if not hasattr(self, "custom_shape"):

from mathutils import Matrix


def draw_arrow_shape(target, shoulder, width, is_3d=False):
    v = shoulder - target
    mat = Matrix.Rotation(math.pi / 2, (3 if is_3d else 2), "Z")
    v.rotate(mat)
    v.length = abs(width / 2)

    return (
        target,
        ((shoulder + v)),
        ((shoulder - v)),
        target,
    )


def get_arrow_size(co, dist, rv3d):
    scale = functions.get_scale_from_pos(co, rv3d)
    length = math.copysign(
        min(
            scale * GIZMO_ARROW_SCALE,
            abs(dist * 0.8),
        ),
        dist,
    )

    width = length * 0.4
    return length, width


class VIEW3D_GT_slvs_distance(Gizmo, ConstarintGizmoGeneric):
    bl_idname = "VIEW3D_GT_slvs_distance"
    type = class_defines.SlvsDistance.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _create_shape(self, context, constr, select=False):
        dist = constr.value / 2 / context.preferences.system.ui_scale
        offset = self.target_get_value("offset")
        overshoot = math.copysign(0.04, offset)

        helplines = (
            (-dist, offset + overshoot, 0.0),
            (-dist, 0.0, 0.0),
            (dist, offset + overshoot, 0.0),
            (dist, 0.0, 0.0),
        )

        p1 = Vector((-dist, offset, 0.0))
        p2 = Vector((dist, offset, 0.0))

        rv3d = context.region_data

        arrow_1 = get_arrow_size(self.matrix_world @ p1, dist, rv3d)
        arrow_2 = get_arrow_size(self.matrix_world @ p2, dist, rv3d)

        coords = (
            *draw_arrow_shape(
                p1, p1 + Vector((arrow_1[0], 0, 0)), arrow_1[1], is_3d=True
            ),
            p1,
            p2,
            *draw_arrow_shape(
                p2, p2 - Vector((arrow_2[0], 0, 0)), arrow_2[1], is_3d=True
            ),
            *(helplines if not select else ()),
        )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GT_slvs_angle(Gizmo, ConstarintGizmoGeneric):
    bl_idname = "VIEW3D_GT_slvs_angle"
    type = class_defines.SlvsAngle.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _create_shape(self, context, constr, select=False):
        angle = abs(constr.value)

        radius = self.target_get_value("offset")
        overshoot = math.copysign(0.04, radius)

        helplines = (
            (0.0, 0.0),
            functions.pol2cart(radius + overshoot, angle / 2),
            (0.0, 0.0),
            functions.pol2cart(radius + overshoot, -angle / 2),
        )

        offset = -angle / 2
        rv3d = context.region_data

        p1 = functions.pol2cart(radius, offset)
        p2 = functions.pol2cart(radius, offset + angle)

        lengths, widths = [], []
        for p in (p1, p2):
            scale = functions.get_scale_from_pos(self.matrix_world @ p.to_3d(), rv3d)

            length = min(
                scale * GIZMO_ARROW_SCALE,
                abs(0.8 * radius * constr.value / 2),
            )
            lengths.append(length)
            widths.append(length * 0.4)

        u = math.pi * radius * 2
        a = abs(length * 360 / u)

        arrow_angle = math.radians(90 + a / 2)

        p1_s = p1.copy()
        p1_s.rotate(Matrix.Rotation(arrow_angle, 2, "Z"))
        p1_s.length = abs(lengths[0])

        p2_s = p2.copy()
        p2_s.rotate(Matrix.Rotation(-arrow_angle, 2, "Z"))
        p2_s.length = abs(lengths[1])

        coords = (
            *draw_arrow_shape(p1, p1 + p1_s, widths[0]),
            *functions.coords_arc_2d(
                0, 0, radius, 32, angle=angle, offset=offset, type="LINES"
            ),
            *draw_arrow_shape(p2, p2 + p2_s, widths[1]),
            *(helplines if not select else ()),
        )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GT_slvs_diameter(Gizmo, ConstarintGizmoGeneric):
    bl_idname = "VIEW3D_GT_slvs_diameter"
    type = class_defines.SlvsDiameter.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _create_shape(self, context, constr, select=False):
        angle = math.radians(self.target_get_value("offset"))
        dist = constr.value / 2 / context.preferences.system.ui_scale

        rv3d = context.region_data

        p1 = functions.pol2cart(-dist, angle)
        p2 = functions.pol2cart(dist, angle)

        arrow_1 = get_arrow_size(self.matrix_world @ p1.to_3d(), dist, rv3d)
        arrow_2 = get_arrow_size(self.matrix_world @ p2.to_3d(), dist, rv3d)

        coords = (
            *draw_arrow_shape(
                p1, functions.pol2cart(arrow_1[0] - dist, angle), arrow_1[1]
            ),
            p1,
            p2,
            *draw_arrow_shape(
                p2, functions.pol2cart(dist - arrow_2[0], angle), arrow_2[1]
            ),
        )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GGT_slvs_preselection(GizmoGroup):
    bl_idname = "VIEW3D_GGT_slvs_preselection"
    bl_label = "preselection ggt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    # NOTE: it woud be great to expose the hovered entity as a gizmogroup prop
    # rather than using global variables...

    @classmethod
    def poll(cls, context):
        return context_mode_check(context, cls.bl_idname)

    def setup(self, context):
        self.gizmo = self.gizmos.new(VIEW3D_GT_slvs_preselection.bl_idname)


specific_constraint_types = ("angle", "diameter", "distance")


def generic_constraints(context):
    """Iterate through constraints which don't have a specific gizmo"""
    constrs = context.scene.sketcher.constraints
    for prop_list in constrs.rna_type.properties:
        name = prop_list.identifier
        if name in ("name", "rna_type", *specific_constraint_types):
            continue
        list = getattr(constrs, name)

        for entity in list:
            yield entity


# TODO: This could alrady Skip entities and constraints that are not active
# TODO: only store indices instead of actual objects
def constraints_mapping(context):
    # Get a constraints per entity mapping
    entities = []
    constraints = []
    for c in generic_constraints(context):
        for e in c.entities():
            if e not in entities:
                entities.append(e)
                # i = len(entities)
            i = entities.index(e)
            if i >= len(constraints):
                constraints.append([])
            constrs = constraints[i]
            if c not in constrs:
                constrs.append(c)
    assert len(entities) == len(constraints)
    return entities, constraints


def set_gizmo_colors(gz, failed):
    theme = functions.get_prefs().theme_settings
    color = theme.constraint.failed if failed else theme.constraint.default
    color_highlight = (
        theme.constraint.failed_highlight if failed else theme.constraint.highlight
    )

    gz.color = color[0:-1]
    gz.alpha = color[-1]
    gz.color_highlight = color_highlight[0:-1]
    gz.alpha_highlight = color_highlight[-1]


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D"}

    def _list_from_type(self, context):
        return context.scene.sketcher.constraints.get_list(self.type)

    def setup(self, context):
        for c in self._list_from_type(context):
            if not c.is_active(context.scene.sketcher.active_sketch):
                continue
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = context.scene.sketcher.constraints.get_index(c)

            set_gizmo_colors(gz, c.failed)

            gz.use_draw_modal = True
            gz.target_set_prop("offset", c, "draw_offset")

            props = gz.target_set_operator(
                operators.View3D_OT_slvs_tweak_constraint_value_pos.bl_idname
            )
            props.type = self.type
            props.index = gz.index

    def refresh(self, context):
        # recreate gizmos here!
        self.gizmos.clear()
        self.setup(context)

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True


class VIEW3D_GGT_slvs_distance(GizmoGroup, ConstraintGenericGGT):
    bl_idname = "VIEW3D_GGT_slvs_distance"
    bl_label = "Distance Constraint Gizmo Group"

    type = class_defines.SlvsDistance.type
    gizmo_type = VIEW3D_GT_slvs_distance.bl_idname


class VIEW3D_GGT_slvs_angle(GizmoGroup, ConstraintGenericGGT):
    bl_idname = "VIEW3D_GGT_slvs_angle"
    bl_label = "Angle Constraint Gizmo Group"

    type = class_defines.SlvsAngle.type
    gizmo_type = VIEW3D_GT_slvs_angle.bl_idname


class VIEW3D_GGT_slvs_diameter(GizmoGroup, ConstraintGenericGGT):
    bl_idname = "VIEW3D_GGT_slvs_diameter"
    bl_label = "Angle Diameter Gizmo Group"

    type = class_defines.SlvsDiameter.type
    gizmo_type = VIEW3D_GT_slvs_diameter.bl_idname

def iter_dimenional_constraints(context):
    ssc = context.scene.sketcher.constraints
    collections = [ssc.distance, ssc.diameter, ssc.angle]
    for coll in collections:
        for c in coll:
            yield c

class VIEW3D_GGT_slvs_constraint(GizmoGroup):
    bl_idname = "VIEW3D_GGT_slvs_constraint"
    bl_label = "Constraint Gizmo Group"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True

    def setup(self, context):
        theme = functions.get_prefs().theme_settings
        entities, constraints = constraints_mapping(context)

        for e, constrs in zip(entities, constraints):
            if not hasattr(e, "placement"):
                continue
            if not e.is_visible(context):
                continue

            active_sketch = context.scene.sketcher.active_sketch
            for i, c in enumerate(constrs):
                if not c.is_active(active_sketch):
                    continue
                gz = self.gizmos.new(VIEW3D_GT_slvs_constraint.bl_idname)
                gz.type = c.type
                gz.index = context.scene.sketcher.constraints.get_index(c)

                pos = functions.get_2d_coords(context, e.placement())

                gz.entity_index = e.slvs_index

                ui_scale = context.preferences.system.ui_scale
                scale = functions.get_prefs().gizmo_scale * ui_scale
                offset_base = Vector((scale * 2.2, 0.0))
                offset = offset_base * i * ui_scale

                gz.offset = offset
                gz.scale_basis = scale

                set_gizmo_colors(gz, c.failed)

                gz.use_draw_modal = True

                if hasattr(c, "draw_props"):
                    op = operators.View3D_OT_slvs_context_menu.bl_idname
                else:
                    op = operators.View3D_OT_slvs_delete_constraint.bl_idname

                props = gz.target_set_operator(op)
                props.type = c.type
                props.index = gz.index

        # Add value gizmos for dimensional constraints
        for c in iter_dimenional_constraints(context):
            if not c.is_active(context.scene.sketcher.active_sketch):
                continue

            gz = self.gizmos.new(VIEW3D_GT_slvs_constraint_value.bl_idname)
            index = context.scene.sketcher.constraints.get_index(c)
            gz.type = c.type
            gz.index = index

            props = gz.target_set_operator(operators.View3D_OT_slvs_context_menu.bl_idname)
            props.type = c.type
            props.index = index

    def refresh(self, context):
        # recreate gizmos here!
        self.gizmos.clear()
        self.setup(context)


classes = (
    VIEW3D_GT_slvs_preselection,
    VIEW3D_GT_slvs_constraint,
    VIEW3D_GT_slvs_distance,
    VIEW3D_GT_slvs_angle,
    VIEW3D_GT_slvs_diameter,
    VIEW3D_GT_slvs_constraint_value,
    VIEW3D_GGT_slvs_preselection,
    VIEW3D_GGT_slvs_constraint,
    VIEW3D_GGT_slvs_distance,
    VIEW3D_GGT_slvs_angle,
    VIEW3D_GGT_slvs_diameter,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
