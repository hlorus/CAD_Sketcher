"""Author the documentation screenshots of the part / feature list.

Shoots the demo scene from ``make_part_list_demo.py`` once per state the list
can be in, cropped to the band that holds the viewport, the Sketcher sidebar and
the outliner. Needs a real GUI, so run it inside the invisible compositor
described in CLAUDE.md::

    blender --factory-startup -p 0 0 1500 740 part_list.blend \
        --python scripts/make_part_list_shots.py -- docs/content/images

The window size matters: the crop below is measured from it, and the panels have
to fit. Re-tune ``CONTENT_HEIGHT`` if the layout changes.
"""

import os
import sys

import addon_utils
import bpy
import numpy as np

TARGET = "bl_ext.user_default.CAD_Sketcher"
addon_utils.disable("bl_ext.blend.CAD_Sketcher", default_set=False)
addon_utils.enable(TARGET, default_set=True)

OUT = sys.argv[sys.argv.index("--") + 1]
# How far down the interesting part of the window reaches: the viewport's
# geometry, the Sketcher panels and the outliner rows all sit above this.
CONTENT_HEIGHT = 490
os.makedirs(OUT, exist_ok=True)
log = []


def only_sketcher_tab():
    """Leave the Sketcher category as the only one, so it is the active tab.

    ``Region.active_panel_category`` is read-only, so the tab cannot be chosen
    directly; dropping every other category from the sidebar is what is left.
    """
    dropped = 0
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name, None)
        if (
            getattr(cls, "bl_space_type", None) == "VIEW_3D"
            and getattr(cls, "bl_region_type", None) == "UI"
            and getattr(cls, "bl_category", None) not in (None, "Sketcher")
        ):
            try:
                bpy.utils.unregister_class(cls)
                dropped += 1
            except Exception:
                pass
    return dropped


def window():
    """The window, from the manager: ``context.window`` is None after a close."""
    return bpy.context.window or bpy.context.window_manager.windows[0]


def areas():
    return {a.type: a for a in window().screen.areas}


def view3d_override(area):
    for region in area.regions:
        if region.type == "WINDOW":
            return {
                "window": window(),
                "area": area,
                "region": region,
                "space_data": area.spaces.active,
                "region_data": area.spaces.active.region_3d,
            }
    return None


def crop(path, box):
    """Crop ``path`` in place to ``box`` = (left, top, right, bottom) in pixels."""
    img = bpy.data.images.load(path)
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    # Blender images are bottom-up; the box is given top-down.
    rows = buf.reshape(h, w, 4)[::-1]
    left, top, right, bottom = box
    cut = rows[top:bottom, left:right]
    ch, cw = cut.shape[:2]

    out = bpy.data.images.new("crop", width=cw, height=ch, alpha=True)
    out.pixels.foreach_set(cut[::-1].ravel())
    out.file_format = "PNG"
    out.filepath_raw = path
    out.save()
    bpy.data.images.remove(out)
    bpy.data.images.remove(img)
    return cw, ch


def shot(name, active, hide=None):
    ctx = bpy.context
    for obj in ctx.selected_objects:
        obj.select_set(False)
    target = bpy.data.objects.get(active) if active else None
    ctx.view_layer.objects.active = target
    if target is not None and target.visible_get():
        target.select_set(True)

    if hide is not None:
        bpy.ops.view3d.slvs_set_part_visibility(part_name=hide)

    for area in ctx.window.screen.areas:
        area.tag_redraw()
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)

    path = os.path.join(OUT, name)
    bpy.ops.screen.screenshot(filepath=path)

    win = window()
    a = areas()
    # Keep the 3D view (with its sidebar) and the right-hand column; drop the
    # top bar above them, and everything below the panels: the timeline, the
    # sliver of properties editor and the empty floor of the viewport.
    top = win.height - (a["VIEW_3D"].y + a["VIEW_3D"].height)
    bottom = min(top + CONTENT_HEIGHT, win.height - a["VIEW_3D"].y)
    size = crop(path, (0, top, win.width, bottom))
    log.append(f"{name}: {size[0]}x{size[1]}")


def run():
    log.append(f"dropped {only_sketcher_tab()} non-Sketcher panels")
    a = areas()

    # Give the outliner most of the right column. The divider is moved rather
    # than the properties editor closed: closing an area from a timer crashes
    # Blender, and a small strip of properties left under it costs nothing.
    outliner = a.get("OUTLINER")
    props = a.get("PROPERTIES")
    if outliner is not None and props is not None:
        edge_y = outliner.y - 1
        edge_x = outliner.x + outliner.width // 2
        try:
            bpy.ops.screen.area_move(
                x=edge_x, y=edge_y, delta=-(outliner.y - props.y - 120)
            )
        except Exception as exc:
            log.append(f"area_move failed: {exc}")
    a = areas()
    log.append(
        "areas: " + ", ".join(f"{t} {x.width}x{x.height}" for t, x in sorted(a.items()))
    )

    view = a["VIEW_3D"]
    space = view.spaces.active
    space.show_region_ui = True
    # The toolbar is not what these shots are about, and it eats the left third.
    space.show_region_toolbar = False
    space.overlay.show_cursor = False
    override = view3d_override(view)
    with bpy.context.temp_override(**override):
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_orbit(angle=0.6, type="ORBITRIGHT")
        bpy.ops.view3d.view_orbit(angle=0.35, type="ORBITUP")
        # Frame the parts rather than the whole scene: view_all includes the
        # origin planes and leaves the geometry small.
        bpy.ops.object.select_all(action="DESELECT")
        for name in ("Bracket", "Plate", "Imported Block"):
            ob = bpy.data.objects.get(name)
            if ob is not None and ob.visible_get():
                ob.select_set(True)
        bpy.ops.view3d.view_selected()
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)

        # One per state the page shows. The demo scene holds more than these
        # (a part with a single feature, a part never drawn); shoot them too if
        # the page ever needs them.
        shot("part_list_all_parts.png", None)
        shot("part_list_assembly.png", "Frame")
        shot("part_list_features.png", "Bracket")
        shot("part_list_hidden.png", "Bracket", hide="Bracket")

    print("\n--- SHOTS ---")
    for line in log:
        print(line)
    print("--- END ---")
    sys.stdout.flush()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(run, first_interval=1.5)
