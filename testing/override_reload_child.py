"""Blender-side steps of the override reload tests, run as separate processes.

``blender -b --factory-startup --python override_reload_child.py -- <step> ...``
where ``<step>`` is one of:

- ``library <package> <path> [old]``: write a library holding one part. With
  ``old`` the object links are left unflagged, as older versions saved them. The
  sketch is drawn on a face of a second object, which it also projects from.
- ``override <package> <library> <main>``: link the library, override the part
  and save the result.
- ``report <package> <main>``: open the file and print one ``RESULT`` line of
  JSON describing what each local override still points at.
"""

import importlib
import json
import sys

import addon_utils
import bmesh
import bpy


def _module(package, name):
    return importlib.import_module(f"{package}.{name}")


def _kind(value):
    if not isinstance(value, bpy.types.ID):
        return None
    if value.library is not None:
        return "linked"
    return "override" if value.override_library is not None else "local"


def make_library(package, path, old):
    context = bpy.context
    scene = context.scene
    body_mod = _module(package, "utilities.body")
    add_sketch = _module(package, "operators.add_sketch")
    curve_ref = _module(package, "model.curve_ref")

    face_anchor = _module(package, "utilities.face_anchor")

    scene.sketcher.entities.ensure_origin_elements(context)
    mesh = bpy.data.meshes.new("plate")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(mesh)
    bm.free()
    plate = bpy.data.objects.new("plate", mesh)
    scene.collection.objects.link(plate)
    top = next(p.index for p in mesh.polygons if p.normal.z > 0.9)
    plane = add_sketch.create_face_workplane(context, plate, top)
    sketch = add_sketch.build_sketch_on_workplane(context, plane)
    start = curve_ref.PointRef.create(sketch, (0, 0), fixed=True)
    end = curve_ref.PointRef.create(sketch, (1, 0))
    curve_ref.LineRef.create(sketch, start, end)
    sketch_obj = sketch.target_object
    sketch_obj.slvs_project_sources.add().source = plate
    body = body_mod.body_of(sketch_obj)
    if old:
        body.property_overridable_library_set(body_mod.BODY_SKETCH_PATH, False)
        plane.property_overridable_library_set(face_anchor.WP_SOURCE_PATH, False)
    bpy.data.libraries.write(path, {sketch_obj, plane, body, plate}, fake_user=True)


def make_override(package, library, main):
    scene = bpy.context.scene
    body_mod = _module(package, "utilities.body")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    with bpy.data.libraries.load(library, link=True) as (src, dst):
        dst.objects = list(src.objects)
    for obj in dst.objects:
        scene.collection.objects.link(obj)
    body = next(obj for obj in dst.objects if body_mod.is_body(obj))
    body.override_hierarchy_create(scene, bpy.context.view_layer)
    bpy.ops.wm.save_as_mainfile(filepath=main)


def report(package, main):
    body_mod = _module(package, "utilities.body")
    face_anchor = _module(package, "utilities.face_anchor")
    bpy.ops.wm.open_mainfile(filepath=main)
    result = {}
    for obj in bpy.data.objects:
        if obj.override_library is None or obj.library is not None:
            continue
        entry = {
            "workplane": _kind(obj.slvs_workplane),
            "body": _kind(obj.slvs_body),
        }
        if body_mod.is_body(obj):
            entry["body_of"] = _kind(obj.get(body_mod.BODY_SKETCH_KEY))
        if face_anchor.KEY_SOURCE in obj:
            entry["wp_source"] = _kind(obj[face_anchor.KEY_SOURCE])
        if len(obj.slvs_project_sources):
            entry["project_source"] = _kind(obj.slvs_project_sources[0].source)
        result[obj.name] = entry
    print("RESULT " + json.dumps(result))


def main():
    step, package, *args = sys.argv[sys.argv.index("--") + 1 :]
    addon_utils.enable(package, default_set=True)
    if step == "library":
        make_library(package, args[0], len(args) > 1 and args[1] == "old")
    elif step == "override":
        make_override(package, args[0], args[1])
    elif step == "report":
        report(package, args[0])


main()
