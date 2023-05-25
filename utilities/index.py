import enum
from typing import List, Tuple


class AlphaTestBits(enum.Flag):
    match = enum.auto()
    full_id = enum.auto()


BIT_DEPTH = 8
MAX_COLOR = (2 ** BIT_DEPTH) - 1
MAX_OVERLAP = (BIT_DEPTH * 4) - len(AlphaTestBits)


_selection_to_index = {}
_index_to_selection = {}


def update_selection_map(entities: List['SlvsGenericEntity']):
    for index, entity in enumerate(entities):
        if index >= MAX_OVERLAP:
            break

        _selection_to_index[index] = entity.slvs_index
        _index_to_selection[entity.slvs_index] = index


def index_to_rgba(index: int) -> Tuple[float, float, float, float]:
    indexed = _index_to_selection.get(index)

    if indexed is not None:
        color_int = 0b1 << indexed + len(AlphaTestBits)
        color_int |= AlphaTestBits.match.value
        a, b, g, r = (
            (
                (color_int & (MAX_COLOR << BIT_DEPTH * channel))
                >> BIT_DEPTH * channel
            ) / MAX_COLOR
            for channel in range(4)
        )
        return r, g, b, a

    r = (index >>  0 & 0xFF) / 0xFF
    g = (index >>  8 & 0xFF) / 0xFF
    b = (index >> 16 & 0xFF) / 0xFF
    return r, g, b, 1.0


def rgb_to_index(r: int, g: int, b: int) -> int:
    return int(sum((
        r <<  0,
        g <<  8,
        b << 16,
    )))


def rgba_to_indices(r: int, g: int, b: int, a: int) -> List[int]:
    alpha_test = AlphaTestBits(a & 0b11)

    if AlphaTestBits.match not in alpha_test:
        return []

    if AlphaTestBits.full_id in alpha_test:
        return [rgb_to_index(r, g, b)]

    color_int = sum((
        r << BIT_DEPTH * 3,
        g << BIT_DEPTH * 2,
        b << BIT_DEPTH * 1,
        a << BIT_DEPTH * 0,
    ))
    indices = []

    for index, bitmask in enumerate((
        0b1 << (bit + len(AlphaTestBits))
        for bit in range(MAX_OVERLAP)
    )):
        if color_int & bitmask:
            indices.append(_selection_to_index[index])

    return indices


def breakdown_index(index: int):
    # See SlvsEntities._set_index for the reverse operation
    type_index = index >> 20
    local_index = index & 0xFFFFF
    return type_index, local_index


def assemble_index(type_index: int, local_index: int):
    return type_index << 20 | local_index


from ..model.base_entity import SlvsGenericEntity  # noqa
