import bpy, bgl, gpu
from . import functions, operators, global_data, class_defines


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
        elif global_data.hover != None:
            context.area.tag_redraw()
            global_data.hover = None

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
GIZMO_GENERIC_SCALE = 5
GIZMO_ROW_OFFSET = Vector((GIZMO_GENERIC_SCALE * 2.2, 0.0))


class VIEW3D_GT_slvs_constraint(Gizmo):
    bl_idname = "VIEW3D_GT_slvs_constraint"

    __slots__ = (
        "custom_shape",
        "type",
        "index",
        "entity_index",
        "offset",
    )

    def _get_constraint(self, context):
        return context.scene.sketcher.constraints.get_from_type_index(
            self.type, self.index
        )

    def _update_matrix_basis(self, context):
        constr = self._get_constraint(context)

        pos = None
        if hasattr(self, "entity_index"):
            entity = context.scene.sketcher.entities.get(self.entity_index)
            if not entity or not hasattr(entity, "placement"):
                return

            pos = functions.get_2d_coords(context, entity.placement())
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
        self._update_matrix_basis(context)
        self.draw_custom_shape(self.custom_shape)

    def draw_select(self, context, select_id):
        self._update_matrix_basis(context)
        self.draw_custom_shape(self.custom_shape, select_id=select_id)

    def setup(self):
        if not hasattr(self, "custom_shape"):
            self.custom_shape = self.new_custom_shape("TRIS", custom_shape_verts)


import math
from mathutils.geometry import intersect_line_plane


class ConstarintGizmoGeneric:
    def _get_constraint(self, context):
        return context.scene.sketcher.constraints.get_from_type_index(
            self.type, self.index
        )

    def _update_matrix_basis(self, constr):
        self.matrix_basis = constr.matrix_basis()

    def setup(self):
        pass

    def draw(self, context):
        constr = self._get_constraint(context)
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

        length = math.copysign(min(0.2, abs(dist * 0.8)), dist)
        width = length * 0.4
        coords = (
            *draw_arrow_shape(p1, p1 + Vector((length, 0, 0)), width, is_3d=True),
            p1,
            p2,
            *draw_arrow_shape(p2, p2 - Vector((length, 0, 0)), width, is_3d=True),
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
        angle = math.radians(constr.value)

        # NOTE: magic factor 0.65, why is this needed?!
        radius = self.target_get_value("offset") * 0.80
        overshoot = math.copysign(0.04, radius)

        helplines = (
            (0.0, 0.0),
            functions.pol2cart(radius + overshoot, angle / 2),
            (0.0, 0.0),
            functions.pol2cart(radius + overshoot, -angle / 2),
        )

        offset = -angle / 2

        length = min(0.2, abs(0.8 * math.pi * radius * constr.value / 360))
        width = length * 0.4

        u = math.pi * radius * 2
        a = abs(length * 360 / u)

        arrow_angle = math.radians(90 + a / 2)

        p1 = Vector(functions.pol2cart(radius, offset))
        p1_s = p1.copy()
        p1_s.rotate(Matrix.Rotation(arrow_angle, 2, "Z"))
        p1_s.length = abs(length)

        p2 = Vector(functions.pol2cart(radius, offset + angle))
        p2_s = p2.copy()
        p2_s.rotate(Matrix.Rotation(-arrow_angle, 2, "Z"))
        p2_s.length = abs(length)

        coords = (
            *draw_arrow_shape(p1, p1 + p1_s, width),
            *functions.coords_arc_2d(
                0, 0, radius, 32, angle=angle, offset=offset, type="LINES"
            ),
            *draw_arrow_shape(p2, p2 + p2_s, width),
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

        length = math.copysign(min(0.2, abs(dist * 0.8)), dist)
        width = length * 0.4

        p1 = Vector(functions.pol2cart(-dist, angle))
        p2 = Vector(functions.pol2cart(dist, angle))
        coords = (
            *draw_arrow_shape(
                p1, Vector(functions.pol2cart(length - dist, angle)), width
            ),
            p1,
            p2,
            *draw_arrow_shape(
                p2, Vector(functions.pol2cart(dist - length, angle)), width
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


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D"}

    def _list_from_type(self, context):
        return context.scene.sketcher.constraints.get_list(self.type)

    def setup(self, context):
        theme = functions.get_prefs().theme_settings
        for c in self._list_from_type(context):
            if not c.is_active(context):
                continue
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = context.scene.sketcher.constraints.get_index(c)

            gz.color = (
                theme.constraint.default if not c.failed else theme.constraint.failed
            )
            gz.alpha = (
                theme.constraint.alpha
                if not c.failed
                else theme.constraint.failed_alpha
            )
            gz.color_highlight = theme.constraint.highlight
            gz.alpha_highlight = theme.constraint.alpha_highlight
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

            for i, c in enumerate(constrs):
                if not c.is_active(context):
                    continue
                gz = self.gizmos.new(VIEW3D_GT_slvs_constraint.bl_idname)
                gz.type = c.type
                gz.index = context.scene.sketcher.constraints.get_index(c)

                pos = functions.get_2d_coords(context, e.placement())

                gz.entity_index = e.slvs_index
                gz.offset = GIZMO_ROW_OFFSET * i * context.preferences.system.ui_scale

                gz.scale_basis = GIZMO_GENERIC_SCALE
                gz.color = (1.0, 0.5, 0.0) if not c.failed else theme.constraint.failed
                gz.alpha = (
                    theme.constraint.alpha
                    if not c.failed
                    else theme.constraint.failed_alpha
                )
                gz.color_highlight = 1.0, 1.0, 1.0
                gz.alpha_highlight = 0.8
                gz.use_draw_modal = True

                props = gz.target_set_operator(
                    operators.View3D_OT_slvs_delete_constraint.bl_idname
                )
                props.type = c.type
                props.index = gz.index

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
