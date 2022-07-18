import bpy, bgl, gpu, blf

from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from . import functions, operators, global_data, class_defines, icon_manager
from .declarations import GizmoGroups, Gizmos, Operators
from .draw_handler import ensure_selection_texture

# NOTE: idealy gizmo would expose active element as a property and
# operators would access hovered element from there
class VIEW3D_GT_slvs_preselection(Gizmo):
    bl_idname = Gizmos.Preselection

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        # reset gizmo highlight
        if global_data.highlight_constraint:
            global_data.highlight_constraint = None
            context.area.tag_redraw()

        if global_data.highlight_entities:
            global_data.highlight_entities.clear()
            context.area.tag_redraw()

        # ensure selection texture is up to date
        # TODO: avoid dependency on operators module?
        ensure_selection_texture(context)

        # sample selection texture and mark hovered entity
        mouse_x, mouse_y = location

        buffer = bgl.Buffer(bgl.GL_FLOAT, 4)
        offscreen = global_data.offscreen
        if not offscreen:
            return -1
        with offscreen.bind():
            bgl.glPixelStorei(bgl.GL_UNPACK_ALIGNMENT, 1)
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


GIZMO_OFFSET = Vector((10.0, 10.0))
GIZMO_GENERIC_SIZE = 5

class ConstraintGizmo:
    def _get_constraint(self, context):
        return context.scene.sketcher.constraints.get_from_type_index(
            self.type, self.index
        )

    def _set_colors(self, context, constraint):
        """Overwrite default color when gizmo is highlighted"""

        theme = functions.get_prefs().theme_settings
        is_highlight = (constraint == global_data.highlight_constraint or self.is_highlight)
        failed = constraint.failed

        if is_highlight:
            col = theme.constraint.failed_highlight if failed else theme.constraint.highlight
        else:
            col = theme.constraint.failed if failed else theme.constraint.default

        self.color = col[:3]
        return col

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
        if not context.scene.sketcher.selectable_constraints:
            return -1

        location = Vector(location).to_3d()
        location -= self.matrix_basis.translation
        location *= 1.0 / self.scale_basis
        import math

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
            ui_scale = context.preferences.system.ui_scale
            scale = self.scale_basis * ui_scale
            gpu.matrix.scale(Vector((scale, scale)))
            icon_manager.draw(self.type, col)

    def setup(self):
        pass


import math
from mathutils.geometry import intersect_line_plane


def _get_formatted_value(context, constr):
    from . import units
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


class VIEW3D_GT_slvs_constraint_value(ConstraintGizmo, Gizmo):
    """Display the value of a dimensional constraint"""
    bl_idname = Gizmos.ConstraintValue

    __slots__ = (
        "type",
        "index",
        "width",
        "height"
    )

    def test_select(self, context, location):
        if not context.scene.sketcher.selectable_constraints:
            return -1

        coords = Vector(location) - self.matrix_basis.translation.to_2d()

        width, height = self.width, self.height
        if -width/2 < coords.x < width/2 and -height/2 < coords.y < height/2:
            return 0
        return -1

    def draw(self, context):
        constr = self._get_constraint(context)

        if not constr.visible or not hasattr(constr, "value_placement"):
            return

        prefs = functions.get_prefs()
        theme = prefs.theme_settings
        color = theme.constraint.text_highlight if self.is_highlight else theme.constraint.text
        text = _get_formatted_value(context, constr)
        font_id = 0
        dpi = context.preferences.system.dpi
        text_size = prefs.text_size

        blf.color(font_id, *color)
        blf.size(font_id, text_size, dpi)
        self.width, self.height = blf.dimensions(font_id, text)

        margin = text_size / 4

        pos = constr.value_placement(context)
        if not pos:
            return
        self.matrix_basis = Matrix.Translation(pos.to_3d()) # Update Matrix for selection

        blf.position(font_id, pos[0]-self.width/2, pos[1] + margin, 0)
        blf.draw(font_id, text)

    def setup(self):
        self.width = 0
        self.height = 0


class ConstraintGizmoGeneric(ConstraintGizmo):
    def _update_matrix_basis(self, constr):
        self.matrix_basis = constr.matrix_basis()

    def setup(self):
        pass

    def draw(self, context):
        constr = self._get_constraint(context)
        if not constr.visible:
            return
        self._set_colors(context, constr)
        self._update_matrix_basis(constr)

        self._create_shape(context, constr)
        self.draw_custom_shape(self.custom_shape)

    def draw_select(self, context, select_id):
        if not context.scene.sketcher.selectable_constraints:
            return

        constr = self._get_constraint(context)
        if not constr.visible:
            return
        self._create_shape(context, constr, select=True)
        self.draw_custom_shape(self.custom_shape, select_id=select_id)


# NOTE: Idealy the geometry batch wouldn't be recreated every redraw,
# however the geom changes with the distance value, maybe at least track changes for that value
# if not hasattr(self, "custom_shape"):

from mathutils import Matrix


def draw_arrow_shape(target, shoulder, width, is_3d=False):
    v = shoulder - target
    mat = Matrix.Rotation(math.pi / 2, (3 if is_3d else 2), "Z")
    v.rotate(mat)
    v.length = abs(width / 2)

    return (
        ((shoulder + v)),
        target,
        target,
        ((shoulder - v)),
        ((shoulder - v)),
        ((shoulder + v)),
    )


def get_overshoot(scale, dir):
    if dir == 0:
        return 0
    #use factor of 0.005 for one-half arrowhead
    overshoot = scale * 0.005 * functions.get_prefs().arrow_scale
    return -math.copysign(overshoot, dir)


def get_arrow_size(dist, scale):
    size = scale * 0.01 * functions.get_prefs().arrow_scale
    size = min(size, abs(dist * 0.67))
    size = math.copysign(size, dist)
    return size, size / 2


class VIEW3D_GT_slvs_distance(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Distance
    type = class_defines.SlvsDistance.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _get_helplines(self, context, constr, scale_1, scale_2):
        ui_scale = context.preferences.system.ui_scale
        dist = constr.value / 2 / ui_scale
        offset = self.target_get_value("offset")
        entity1, entity2 = constr.entity1, constr.entity2
        if entity1.is_line():
            entity1, entity2 = entity1.p1, entity1.p2

        # Get constraints points in local space and adjust helplines based on their position
        mat_inv = constr.matrix_basis().inverted()

        def get_local(point):
            return (mat_inv @ point.location.to_3d()) / ui_scale

        # Store the two endpoints of the helplines in local space
        points_local = []
        points_local.append(get_local(entity1))

        if type(entity2) in class_defines.point:
            points_local.append(get_local(entity2))

        elif type(entity2) in class_defines.line:
            line_points = (get_local(entity2.p1), get_local(entity2.p2))
            line_points_side = [pos.y - offset > 0 for pos in line_points]

            x = math.copysign(dist, line_points[0].x)
            y = offset

            if line_points_side[0] != line_points_side[1]:
                # Distance line is between line points
                y = offset
            else:
                # Get the closest point
                points_delta = [abs(p.y - offset) for p in line_points]
                i = int(points_delta[0] > points_delta[1])
                y = line_points[i].y
            points_local.append(Vector((x, y, 0.0)))

        # Pick the points based on their x location
        if points_local[0].x > points_local[1].x:
            point_right, point_left = points_local
        else:
            point_right, point_left = reversed(points_local)

        overshoot_1 = offset + get_overshoot(scale_1, point_left.y - offset)
        overshoot_2 = offset + get_overshoot(scale_2, point_right.y - offset)

        return (
            (-dist, overshoot_1, 0.0),
            (-dist, point_left.y, 0.0),
            (dist, overshoot_2, 0.0),
            (dist, point_right.y, 0.0),
        )

    def _create_shape(self, context, constr, select=False):
        rv3d = context.region_data
        ui_scale = context.preferences.system.ui_scale

        half_dist = constr.value / 2 / ui_scale
        offset = self.target_get_value("offset")
        outset = constr.draw_outset

        p1 = Vector((-half_dist, offset, 0.0))
        p2 = Vector((half_dist, offset, 0.0))
        if not constr.text_inside(ui_scale):
            p1, p2 = p2, p1
        p1_global, p2_global = [self.matrix_world @ p for p in (p1, p2)]

        scale_1, scale_2 = [functions.get_scale_from_pos(p, rv3d) for p in (p1_global, p2_global)]

        arrow_1 = get_arrow_size(half_dist, scale_1)
        arrow_2 = get_arrow_size(half_dist, scale_2)

        if constr.text_inside(ui_scale):
            coords = (
                *draw_arrow_shape(
                    p1,
                    p1 + Vector((arrow_1[0], 0, 0)),
                    arrow_1[1],
                    is_3d=True
                ),
                p1,
                p2,
                *draw_arrow_shape(
                    p2,
                    p2 - Vector((arrow_2[0], 0, 0)),
                    arrow_2[1],
                    is_3d=True
                ),
                *(self._get_helplines(context, constr, scale_1, scale_2) if not select else ()),
            )
        else:  # the same thing, but with a little jitter to the outside
            coords = (
                *draw_arrow_shape(
                    p1,
                    p1 + Vector((arrow_1[0], 0, 0)),
                    arrow_1[1],
                    is_3d=True
                ),
                p1,
                Vector((outset, offset, 0)),  # jitter back and forth to extend leader line for text_outside case
                p1,                           # but it is unnecessary work for text_inside case
                p2,
                *draw_arrow_shape(
                    p2,
                    p2 - Vector((arrow_2[0], 0, 0)),
                    arrow_2[1],
                    is_3d=True
                ),
                *(self._get_helplines(context, constr, scale_1, scale_2) if not select else ()),
            )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GT_slvs_angle(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Angle
    type = class_defines.SlvsAngle.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _get_helplines(self, context, constr, scale_1, scale_2):
        angle = abs(constr.value)
        radius = self.target_get_value("offset")

        overshoot_1 = get_overshoot(scale_1, radius)
        overshoot_2 = get_overshoot(scale_2, radius)
        return (
            (0.0, 0.0),
            functions.pol2cart(radius - overshoot_1, angle / 2),
            (0.0, 0.0),
            functions.pol2cart(radius - overshoot_2, -angle / 2),
        )

    def _create_shape(self, context, constr, select=False):

        def get_arrow_angle():
            # The arrowheads are placed on an arc spanning between the
            #     witness lines, and we want them to point "along" this arc.
            # So we rotate the arrowhead by a quarter-turn plus (or minus)
            #     half the amount the arc segment underneath it rotates.
            segment = length / abs(radius)
            rotation = (math.tau/4 + segment/2) if constr.text_inside() else (math.tau/4 - segment/2)
            return rotation

        rv3d = context.region_data

        # note: radius is signed value, but
        # angle, length, lengths[], widths[] are all absolute values
        radius = self.target_get_value("offset")
        angle = abs(constr.value)
        half_angle = angle / 2
        p1 = functions.pol2cart(radius, -half_angle)
        p2 = functions.pol2cart(radius, half_angle)

        scales = []
        lengths, widths = [], []    # Length is limited to no more than 1/3 the span
        for p in (p1, p2):
            scale = functions.get_scale_from_pos(self.matrix_world @ p.to_3d(), rv3d)
            scales.append(scale)

            length = min(
                abs(get_arrow_size(radius, scale)[0]),
                abs(radius * (angle/3)),
            )
            lengths.append(length)
            widths.append(length * 0.4)

        arrow_angle = get_arrow_angle()

        p1_s = p1.copy()
        p1_s.rotate(Matrix.Rotation(arrow_angle, 2, "Z"))
        p1_s.length = lengths[0]

        p2_s = p2.copy()
        p2_s.rotate(Matrix.Rotation(-arrow_angle, 2, "Z"))
        p2_s.length = lengths[1]

        if constr.text_inside():
            coords = (
                *draw_arrow_shape(p1, p1 + p1_s, widths[0]),
                *functions.coords_arc_2d(
                    0, 0, radius, 32, angle=angle, offset=-half_angle, type="LINES"
                ),
                *draw_arrow_shape(p2, p2 + p2_s, widths[1]),
                *(self._get_helplines(context, constr, *scales) if not select else ()),
            )
        else:
            leader_end = constr.draw_outset # signed angle, measured from the Constrained Angle's bisector
            leader_start = math.copysign(half_angle, -leader_end)
            leader_length = leader_end - leader_start
            coords = (
                *draw_arrow_shape(p1, p1 - p1_s, widths[0]),
                *functions.coords_arc_2d(
                    0, 0, radius, 16, angle=leader_length, offset=leader_start, type="LINES"
                ),
                *draw_arrow_shape(p2, p2 - p2_s, widths[1]),
                *(self._get_helplines(context, constr, *scales) if not select else ()),
            )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GT_slvs_diameter(Gizmo, ConstraintGizmoGeneric):
    bl_idname = Gizmos.Diameter
    type = class_defines.SlvsDiameter.type

    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 1},)

    __slots__ = (
        "custom_shape",
        "index",
    )

    def _create_shape(self, context, constr, select=False):
        ui_scale = context.preferences.system.ui_scale
        angle = constr.leader_angle
        offset = constr.draw_offset / ui_scale
        dist = constr.radius / ui_scale

        rv3d = context.region_data

        p1 = functions.pol2cart(-dist, angle)
        p2 = functions.pol2cart(dist, angle)

        p1_global, p2_global = [self.matrix_world @ p.to_3d() for p in (p1, p2)]
        scale_1, scale_2 = [functions.get_scale_from_pos(p, rv3d) for p in (p1_global, p2_global)]

        arrow_1 = get_arrow_size(dist, scale_1)
        arrow_2 = get_arrow_size(dist, scale_2)

        if constr.setting:
            # RADIUS_MODE:
            #   drawn inside and outside as a single segment
            if constr.text_inside():
                coords = (
                    *draw_arrow_shape(
                        p2, functions.pol2cart(dist - arrow_2[0], angle), arrow_2[1]
                    ),
                    p2,
                    (0,0)
                )
            else:
                coords = (
                    *draw_arrow_shape(
                        p2, functions.pol2cart(arrow_2[0] + dist, angle), arrow_2[1]
                    ),
                    p2,
                    functions.pol2cart(offset, angle),
                )

        else:
            # DIAMETER_MODE:
            #   drawn inside as a single segment
            #   drawn outside as a 2-segment gizmo
            if constr.text_inside():
                coords = (
                    *draw_arrow_shape(
                        p1, functions.pol2cart(arrow_2[0] - dist, angle), arrow_2[1]
                    ),
                    p1,
                    p2,
                    *draw_arrow_shape(
                        p2, functions.pol2cart(dist - arrow_2[0], angle), arrow_2[1]
                    ),
                )
            else:
                coords = (
                    *draw_arrow_shape(
                        p2, functions.pol2cart(arrow_1[0] + dist, angle), arrow_1[1]
                    ),
                    p2,
                    functions.pol2cart(offset, angle),
                    functions.pol2cart(dist + (3 * arrow_2[0]), angle + math.pi), #limit length to 3 arrowheads
                    p1,
                    *draw_arrow_shape(
                        p1, functions.pol2cart(dist + arrow_2[0], angle + math.pi), arrow_2[1]
                    ),
                )

        self.custom_shape = self.new_custom_shape("LINES", coords)


class VIEW3D_GGT_slvs_preselection(GizmoGroup):
    bl_idname = GizmoGroups.Preselection
    bl_label = "preselection ggt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    # NOTE: it would be great to expose the hovered entity as a gizmogroup prop
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


# TODO: This could already Skip entities and constraints that are not active
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

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
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
    bl_idname = GizmoGroups.Distance
    bl_label = "Distance Constraint Gizmo Group"

    type = class_defines.SlvsDistance.type
    gizmo_type = VIEW3D_GT_slvs_distance.bl_idname


class VIEW3D_GGT_slvs_angle(GizmoGroup, ConstraintGenericGGT):
    bl_idname = GizmoGroups.Angle
    bl_label = "Angle Constraint Gizmo Group"

    type = class_defines.SlvsAngle.type
    gizmo_type = VIEW3D_GT_slvs_angle.bl_idname


class VIEW3D_GGT_slvs_diameter(GizmoGroup, ConstraintGenericGGT):
    bl_idname = GizmoGroups.Diameter
    bl_label = "Diameter Gizmo Group"

    type = class_defines.SlvsDiameter.type
    gizmo_type = VIEW3D_GT_slvs_diameter.bl_idname

def iter_dimenional_constraints(context):
    ssc = context.scene.sketcher.constraints
    collections = [ssc.distance, ssc.diameter, ssc.angle]
    for coll in collections:
        for c in coll:
            yield c

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
                offset_base = Vector((scale * 1.0, 0.0))
                offset = offset_base * i * ui_scale

                gz.offset = offset
                gz.scale_basis = scale

                set_gizmo_colors(gz, c.failed)

                gz.use_draw_modal = True

                op = Operators.ContextMenu
                props = gz.target_set_operator(op)
                props.type = c.type
                props.index = gz.index

                props.highlight_hover = True
                props.highlight_members = True

        # Add value gizmos for dimensional constraints
        for c in iter_dimenional_constraints(context):
            if not c.is_active(context.scene.sketcher.active_sketch):
                continue

            gz = self.gizmos.new(VIEW3D_GT_slvs_constraint_value.bl_idname)
            index = context.scene.sketcher.constraints.get_index(c)
            gz.type = c.type
            gz.index = index

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
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
