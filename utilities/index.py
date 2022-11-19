def index_to_rgb(i: int):
    r = (i & int("0x000000FF", 16)) / 255
    g = ((i & int("0x0000FF00", 16)) >> 8) / 255
    b = ((i & int("0x00FF0000", 16)) >> 16) / 255
    return r, g, b


def rgb_to_index(r: int, g: int, b: int) -> int:
    i = int(r * 255 + g * 255 * 256 + b * 255 * 256 * 256)
    return i


def breakdown_index(index: int):
    # See SlvsEntities._set_index for the reverse operation
    type_index = index >> 20
    local_index = index & 0xFFFFF
    return type_index, local_index


def assemble_index(type_index: int, local_index: int):
    return type_index << 20 | local_index
