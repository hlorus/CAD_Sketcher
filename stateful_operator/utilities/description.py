def _format_types(types):
    entity_names = ", ".join([e.__name__ for e in types])
    return "[" + entity_names + "]"


_PICK_TYPE_NAMES = {"MeshPolygon": "face", "MeshVertex": "vertex", "MeshEdge": "edge"}


def pick_types_label(types) -> str:
    """Readable "line or point" style list of pickable element types."""
    names = []
    for t in types:
        name = _PICK_TYPE_NAMES.get(t.__name__)
        if name is None:
            name = t.__name__
            if name.startswith("Slvs"):
                name = name[4:]
            for suffix in ("2D", "3D", "Ref"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            name = name.lower()
        if name not in names:
            names.append(name)
    if len(names) > 1:
        return ", ".join(names[:-1]) + " or " + names[-1]
    return names[0] if names else "element"


def state_desc(name, desc, types):
    type_desc = ""
    if types:
        type_desc = "Types: " + _format_types(types)
    return " ".join((name + ":", desc, type_desc))


def stateful_op_desc(base, *state_descs):
    states = ""
    length = len(state_descs)
    for i, state in enumerate(state_descs):
        states += " - {}{}".format(state, ("  \n" if i < length - 1 else ""))
    desc = "{}  \n  \nStates:  \n{}".format(base, states)
    return desc
