def index_to_rgb(i: int):
    r = ((i & 0x0000ff) >>  0) / 255
    g = ((i & 0x00ff00) >>  8) / 255
    b = ((i & 0xff0000) >> 16) / 255
    return r, g, b


def rgb_to_index(r: int, g: int, b: int) -> int:
    i = (int(r * 255 + 0.5) <<  0) \
      | (int(g * 255 + 0.5) <<  8) \
      | (int(b * 255 + 0.5) << 16)
    return i


def breakdown_index(index: int):
    # See SlvsEntities._set_index for the reverse operation
    type_index = index >> 20
    local_index = index & 0xFFFFF
    return type_index, local_index


def assemble_index(type_index: int, local_index: int):
    return type_index << 20 | local_index
