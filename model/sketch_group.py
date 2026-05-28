"""
Semantic grouping of sketch entities for IFC and other integrations.

A SketchGroup is a named collection of entity references (by slvs_index) stored
on a sketch.  Each group carries an ordered list of IFC class tags, allowing the
same group (and its member entities) to be associated with several IFC classes
simultaneously.  The same entity can also belong to multiple groups, enabling
one-geometry / many-IFC-elements patterns without duplicating CAD geometry.

Classes
-------
SketchGroupTag
    One IFC class label within a :class:`SketchGroup`'s tag list.

SketchGroupMember
    The *relationship* between one entity and one group.  Holds the entity's
    slvs_index plus the per-context GUID (e.g. the IfcWall GlobalId that this
    specific line represents within a wall-run group).

SketchGroup
    One semantic group: a name, an ordered list of IFC class tags, an optional
    group-level GUID, and an ordered list of members.
"""

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, StringProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .. import global_data

_TAG_UPDATE_GUARD = False


def _normalize_tag_value(value: str) -> str:
    return (value or "").strip().casefold()


def _find_tag_owner_collection(context, tag):
    scene = getattr(context, "scene", None)
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return None, -1

    sketches = getattr(scene.sketcher.entities, "sketches", ())
    for sketch in sketches:
        for i, t in enumerate(sketch.tags):
            if t == tag:
                return sketch.tags, i
        for group in sketch.groups:
            for i, t in enumerate(group.tags):
                if t == tag:
                    return group.tags, i

    return None, -1


def _show_duplicate_tag_warning(context):
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return

    def _draw(self, _context):
        self.layout.label(text="Tag already exists in this list", icon="ERROR")

    wm.popup_menu(_draw, title="Duplicate Tag", icon="ERROR")


def _on_tag_value_update(self, context):
    global _TAG_UPDATE_GUARD
    if _TAG_UPDATE_GUARD:
        return

    new_value = (self.value or "").strip()
    if new_value != self.value:
        _TAG_UPDATE_GUARD = True
        self.value = new_value
        _TAG_UPDATE_GUARD = False

    if not new_value:
        self.last_valid_value = ""
        return

    coll, own_index = _find_tag_owner_collection(context, self)
    if coll is None:
        self.last_valid_value = new_value
        return

    new_norm = _normalize_tag_value(new_value)
    duplicate = any(
        i != own_index and _normalize_tag_value(t.value) == new_norm
        for i, t in enumerate(coll)
    )

    if duplicate:
        _TAG_UPDATE_GUARD = True
        self.value = self.last_valid_value
        _TAG_UPDATE_GUARD = False
        _show_duplicate_tag_warning(context)
        return

    self.last_valid_value = new_value

    scene = getattr(context, "scene", None) if context is not None else None
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return

    try:
        from ..utilities.reference_geometry import refresh_reference_geometry

        refresh_reference_geometry(
            context or bpy.context, sketch=scene.sketcher.active_sketch
        )
    except Exception:
        return


class SketchGroupTag(PropertyGroup):
    """One IFC class label in a :class:`SketchGroup`'s tag list.

    ``value`` should be a fully-qualified IFC class name such as ``IfcWall``
    or ``IfcSlab``.
    """

    value: StringProperty(
        name="Tag",
        description="IFC class name (e.g. IfcWall, IfcSlab, IfcCovering)",
        default="",
        update=_on_tag_value_update,
    )
    last_valid_value: StringProperty(
        name="Last Valid Tag",
        default="",
        options={"HIDDEN", "SKIP_SAVE"},
    )
    enabled: BoolProperty(
        name="Enabled",
        description="When disabled this tag is ignored by all callers",
        default=True,
    )


class SketchGroupMember(PropertyGroup):
    """One entity's participation in a SketchGroup.

    The GUID stored here is the IFC GlobalId of *this entity instance* within
    the group's IFC class context.  It may be empty when no individual IFC
    element GUID exists for this piece (e.g. a sub-segment of a slab boundary).
    """

    entity_index: IntProperty(
        name="Entity Index",
        description="slvs_index of the member entity",
        default=-1,
    )
    guid: StringProperty(
        name="GUID",
        description=(
            "IFC GlobalId of this entity instance within the group's IFC class "
            "context.  Leave empty if no individual IFC element GUID applies"
        ),
        default="",
    )


class SketchGroup(PropertyGroup):
    """A named semantic group of sketch entities.

    Members may be associated with one or more IFC classes via the ``tags``
    list.  The same entity may appear as a member of multiple groups, each with
    a different tag set and GUID, allowing the same CAD geometry to represent
    several IFC elements simultaneously.
    """

    name: StringProperty(
        name="Name",
        description="Human-readable label for this group",
        default="Group",
    )
    tags: CollectionProperty(
        name="Tags",
        description="IFC class names associated with this group",
        type=SketchGroupTag,
    )
    active_tag_index: IntProperty(
        name="Active Tag",
        default=-1,
    )
    guid: StringProperty(
        name="Group GUID",
        description=(
            "IFC GlobalId of a container-level abstraction for this group "
            "(optional; leave empty if no such IFC element exists)"
        ),
        default="",
    )
    members: CollectionProperty(
        name="Members",
        type=SketchGroupMember,
    )
    active_member_index: IntProperty(
        name="Active Member",
        default=-1,
        update=lambda self, context: self._sync_member_selection(),
    )

    def _sync_member_selection(self):
        global_data.selected.clear()
        idx = self.active_member_index
        if 0 <= idx < len(self.members):
            entity_index = self.members[idx].entity_index
            if entity_index != -1:
                global_data.selected.append(entity_index)
        global_data.needs_redraw = True

    # ------------------------------------------------------------------
    # Tag helpers
    # ------------------------------------------------------------------

    def has_tag(self, value: str) -> bool:
        """Return ``True`` if *value* is already in the tag list."""
        norm = _normalize_tag_value(value)
        return any(_normalize_tag_value(t.value) == norm for t in self.tags)

    def add_tag(self, value: str) -> "SketchGroupTag":
        """Add *value* as a tag if not already present; return the tag entry."""
        norm = _normalize_tag_value(value)
        for t in self.tags:
            if _normalize_tag_value(t.value) == norm:
                return t
        t = self.tags.add()
        t.value = value.strip()
        self.active_tag_index = len(self.tags) - 1
        return t

    def remove_tag_by_index(self, index: int) -> None:
        """Remove the tag at collection position *index*."""
        self.tags.remove(index)
        if self.active_tag_index >= len(self.tags):
            self.active_tag_index = len(self.tags) - 1

    def remove_tag_by_value(self, value: str) -> None:
        """Remove the first tag whose value equals *value* (no-op if absent)."""
        for i, t in enumerate(self.tags):
            if t.value == value:
                self.remove_tag_by_index(i)
                return

    def tag_values(self) -> list:
        """Return a plain list of enabled tag value strings."""
        return [t.value for t in self.tags if t.enabled]

    # ------------------------------------------------------------------
    # Member helpers
    # ------------------------------------------------------------------

    def add_member(self, slvs_index: int) -> SketchGroupMember:
        """Append *slvs_index* as a new member and return the new record."""
        m = self.members.add()
        m.entity_index = slvs_index
        return m

    def remove_member(self, member_index: int) -> None:
        """Remove the member at *member_index* (collection position)."""
        self.members.remove(member_index)

    def get_member(self, slvs_index: int):
        """Return the :class:`SketchGroupMember` for *slvs_index*, or ``None``."""
        for m in self.members:
            if m.entity_index == slvs_index:
                return m
        return None

    def contains(self, slvs_index: int) -> bool:
        """Return ``True`` if *slvs_index* is already a member of this group."""
        return self.get_member(slvs_index) is not None

    # ------------------------------------------------------------------
    # Path-type computation
    # ------------------------------------------------------------------

    def path_type(self, sse) -> str:
        """Return one of ``'CLOSED_PATH'``, ``'OPEN_PATH'``, or ``'NOT_PATH'``.

        Inspects the group's member entities using their ``connection_points()``
        to determine whether they form a closed loop, an open chain, or neither.
        *sse* is ``context.scene.sketcher.entities``.
        """
        from collections import defaultdict

        entities = [sse.get(m.entity_index) for m in self.members]
        entities = [e for e in entities if e is not None]

        if not entities:
            return "NOT_PATH"

        if not all(hasattr(e, "is_path") and e.is_path() for e in entities):
            return "NOT_PATH"

        # Single entity: closed if it reports so (circle), else open
        if len(entities) == 1:
            e = entities[0]
            if hasattr(e, "is_closed") and e.is_closed():
                return "CLOSED_PATH"
            return "OPEN_PATH"

        if not all(hasattr(e, "connection_points") for e in entities):
            return "NOT_PATH"

        # Map each endpoint (by slvs_index) to the entities that touch it
        point_entities = defaultdict(list)
        for e in entities:
            for p in e.connection_points():
                point_entities[p.slvs_index].append(e.slvs_index)

        # Branching (degree > 2) → not a simple path
        if any(len(v) > 2 for v in point_entities.values()):
            return "NOT_PATH"

        # Build entity adjacency via shared degree-2 points
        adj = defaultdict(set)
        for pt, ent_ids in point_entities.items():
            if len(ent_ids) == 2:
                a, b = ent_ids
                adj[a].add(b)
                adj[b].add(a)

        # BFS connectivity — all entities must be reachable from the first
        start = entities[0].slvs_index
        visited = {start}
        queue = [start]
        all_ids = {e.slvs_index for e in entities}
        while queue:
            cur = queue.pop()
            for nb in adj[cur]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)

        if visited != all_ids:
            return "NOT_PATH"  # disconnected segments

        degree_1 = sum(1 for v in point_entities.values() if len(v) == 1)
        if degree_1 == 0:
            return "CLOSED_PATH"
        if degree_1 == 2:
            return "OPEN_PATH"
        return "NOT_PATH"

    def entities(self, context):
        """Yield ``(entity, member)`` pairs for every member of this group.

        Silently skips stale entries whose slvs_index no longer resolves to a
        live entity (e.g. after the entity was deleted).
        """
        sse = context.scene.sketcher.entities
        for m in self.members:
            e = sse.get(m.entity_index)
            if e is not None:
                yield e, m


register, unregister = register_classes_factory(
    (SketchGroupTag, SketchGroupMember, SketchGroup)
)
