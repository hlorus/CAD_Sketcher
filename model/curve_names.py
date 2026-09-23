"""Names a user gave to sketch entities.

Only renamed entities are stored, keyed by curve id, in a collection on the
Curves datablock. Everything else is named from its type and its ``name_ordinal``
attribute when it is displayed, so no geometry rebuild can lose a name: Blender
wipes STRING attributes on every ``remove_curves``, and the old per-curve name
attribute had to be snapshotted and written back by every path that removed a
curve -- 3 ms per pass on a 2000-curve sketch, on every preview frame.
"""

import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory


class SlvsCurveName(PropertyGroup):
    """One user-given name, bound to a curve id."""

    curve_id: StringProperty(name="Curve ID")
    value: StringProperty(name="Name")


class SlvsCurveNames(PropertyGroup):
    """The renamed entities of one sketch."""

    entries: CollectionProperty(type=SlvsCurveName)

    def _find(self, curve_id: str):
        for entry in self.entries:
            if entry.curve_id == curve_id:
                return entry
        return None

    def get(self, curve_id: str) -> str:
        """The name given to ``curve_id``, or "" when it has none."""
        entry = self._find(curve_id) if curve_id else None
        return entry.value if entry else ""

    def set(self, curve_id: str, value: str) -> None:
        """Name ``curve_id``, or drop the entry when the name is empty."""
        if not curve_id:
            return
        entry = self._find(curve_id)
        if not value:
            if entry is not None:
                self.entries.remove(
                    next(i for i, e in enumerate(self.entries) if e == entry)
                )
            return
        if entry is None:
            entry = self.entries.add()
            entry.curve_id = curve_id
        entry.value = value

    def discard(self, curve_ids) -> None:
        """Forget the names of curves that are gone."""
        keep = set(curve_ids)
        for i in reversed(range(len(self.entries))):
            if self.entries[i].curve_id not in keep:
                self.entries.remove(i)


def custom_names(curve_data):
    """The rename collection of a Curves datablock, or None without one."""
    return getattr(curve_data, "sketch_names", None)


def custom_name(curve_data, curve_id: str) -> str:
    """The name a user gave this curve, or "" when it goes by its type."""
    names = custom_names(curve_data)
    return names.get(curve_id) if names else ""


def set_custom_name(curve_data, curve_id: str, value: str) -> None:
    """Rename a curve, or clear the rename when ``value`` is empty."""
    names = custom_names(curve_data)
    if names is not None:
        names.set(curve_id, value)


_register_classes, _unregister_classes = register_classes_factory(
    (SlvsCurveName, SlvsCurveNames)
)


def register():
    _register_classes()
    bpy.types.Curves.sketch_names = bpy.props.PointerProperty(type=SlvsCurveNames)


def unregister():
    del bpy.types.Curves.sketch_names
    _unregister_classes()
