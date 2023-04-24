import re
from typing import Any, Sequence, Union

import bpy
from bpy.types import Context, Object
from mathutils import Vector


class bpyEnum:
    """
    Helper class to interact with bpy enums

    NOTE: this is currently based on the enum_items list,
    alternatively this could also work on registered EnumProperties
    """

    def __init__(
        self,
        data: Sequence,
        index: Union[int, None] = None,
        identifier: Union[None, str] = None,
    ):
        self.data = data

        if not identifier:
            self.identifier = self._get_identifier(index)
        else:
            self.identifier = identifier
        item = self._get_active_item()

        self.name = item[1]
        self.description = item[2]
        self.index = item[-1]
        if len(item) == 5:
            icon = item[3]
        else:
            icon = None
        self.icon = icon

    def _get_active_item(self):
        i = [item[0] for item in self.data].index(self.identifier)
        return self.data[i]

    def _get_item_index(self, item):
        if len(item) > 3:
            return item[-1]
        return self.data.index(item)

    def _get_identifier(self, index):
        i = [self._get_item_index(item) for item in self.data].index(index)
        return self.data[i][0]


# custom __setattr__ to allow unique attributes in collections,
# use with PropertyGroups which are stored in a collection
# define class attribute "unique_names = ["", ...]" to define what attributes should be handled
# https://blender.stackexchange.com/questions/15122/collectionproperty-avoid-duplicate-names
# cls.__setattr__ = functions.unique_attribute_setter


def unique_attribute_setter(self, name: str, value: Any):
    def collection_from_element(self):
        """Get the collection containing the element"""
        path = self.path_from_id()
        match = re.match("(.*)\[\d*\]", path)
        parent = self.id_data
        try:
            coll_path = match.group(1)
        except AttributeError:
            raise TypeError("Property not element in a collection.")
        else:
            return parent.path_resolve(coll_path)

    def new_val(stem, nbr):
        """Simply for formatting"""
        return "{st}.{nbr:03d}".format(st=stem, nbr=nbr)

    property_func = getattr(self.__class__, name, None)
    if property_func and isinstance(property_func, property):
        # check if name is a property
        super(self.__class__, self).__setattr__(name, value)
        return
    if name not in self.unique_names:
        # don't handle
        self[name] = value
        return
    if value == getattr(self, name):
        # check for assignment of current value
        return

    coll = collection_from_element(self)
    if value not in coll:
        # if value is not in the collection, just assign
        self[name] = value
        return

    # see if value is already in a format like 'name.012'
    match = re.match(r"(.*)\.(\d{3,})", value)
    if match is None:
        stem, nbr = value, 1
    else:
        stem, nbr = match.groups()

    # check for each value if in collection
    new_value = new_val(stem, nbr)
    while new_value in coll:
        nbr += 1
        new_value = new_val(stem, nbr)
    self[name] = new_value


def add_new_empty(context: Context, location: Vector, name="") -> Object:
    """Places an empty at given location, useful for testing"""
    data = bpy.data
    empty = data.objects.new(name, None)
    empty.location = location
    context.collection.objects.link(empty)
    return empty


def setprop(data, key, value):
    """Set an id prop without triggering it's update mehtod"""
    prop = data.rna_type.properties[key]

    # Handle Enums which have to be set by the item's id rather than identifier
    if prop.type == "ENUM":
        value = prop.enum_items[value].value

    data[key] = value
