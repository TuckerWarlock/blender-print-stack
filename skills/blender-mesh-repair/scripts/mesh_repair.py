"""
Mesh repair toolkit. Run inside Blender via `execute_blender_code`, or paste
into the Scripting workspace.

Designed for meshes arriving from outside Blender — image-to-3D generators,
photogrammetry scans, downloaded assets — which are typically dense
non-manifold triangle soup with inconsistent normals and no real scale.

Call order that actually works:
    setup_mm_units()
    o = import_mesh("/path/mask.glb")
    diagnose(o)                       # see what's broken
    scale_to_mm(o, height_mm=240)     # real-world size FIRST
    o = repair(o, voxel_mm=0.8)       # remesh to a watertight manifold
    o = shell(o, thickness_mm=2.5)    # hollow, e.g. for a wearable
    diagnose(o)                       # must be clean before export
    export_stl(o, "/path/mask.stl")   # or export however you like

If the mesh is still a bare open shell (no back, no thickness yet — built
directly as a face surface, not imported as a volume), swap the last two:
shell() before repair(), or repair() will reconstruct only a small fragment
and discard the rest. See repair()'s docstring.
"""

import bmesh
import bpy
from mathutils.bvhtree import BVHTree


# --------------------------------------------------------------------------
# Units. STL is a unitless format and every slicer assumes millimetres, so we
# make 1 Blender unit == 1 mm and export at scale 1. This removes the single
# most common cause of models arriving 1000x too large or too small.
# --------------------------------------------------------------------------
def setup_mm_units():
    u = bpy.context.scene.unit_settings
    u.system = "METRIC"
    u.scale_length = 0.001
    u.length_unit = "MILLIMETERS"
    print("units: 1 Blender unit = 1 mm")


def import_mesh(path):
    """Import glb/obj/stl/ply and return the joined result as one object."""
    before = set(bpy.data.objects)
    low = path.lower()
    if low.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif low.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
    elif low.endswith(".stl"):
        try:
            bpy.ops.wm.stl_import(filepath=path)
        except AttributeError:
            bpy.ops.import_mesh.stl(filepath=path)
    elif low.endswith(".ply"):
        bpy.ops.wm.ply_import(filepath=path)
    else:
        raise ValueError(f"unsupported format: {path}")

    new = [o for o in set(bpy.data.objects) - before if o.type == "MESH"]
    if not new:
        raise RuntimeError("import produced no mesh objects")
    for o in new:                       # drop generated materials; irrelevant for STL
        o.data.materials.clear()
    obj = join(new, name="PRINT-mesh") if len(new) > 1 else new[0]
    obj.name = "PRINT-mesh"
    clear_parents_and_apply(obj)
    print(f"imported {obj.name}: {len(obj.data.polygons):,} faces")
    return obj


def join(objects, name="PRINT-mesh"):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    return obj


def clear_parents_and_apply(obj):
    """glTF import nests objects under rotated empties. Bake that down or every
    later measurement is wrong."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.parent:
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()


def _world_bbox_dims(obj):
    """True world-space bounding box (x, y, z) size.

    obj.dimensions is a local-space measurement scaled by obj.scale — it does
    NOT rotate into world space. Any object whose rotation hasn't been baked
    down (i.e. didn't go through import_mesh()/clear_parents_and_apply, or was
    already sitting in the scene at an angle) will silently report the wrong
    axis as "height"/"width"/"depth". This walks actual vertex world
    coordinates instead, so it's correct regardless of rotation state.
    """
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    zs = [c.z for c in coords]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


# --------------------------------------------------------------------------
# Diagnosis. These are the checks a slicer silently fails on.
# --------------------------------------------------------------------------
def diagnose(obj, verbose=True):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    boundary = [e for e in bm.edges if len(e.link_faces) == 1]     # holes
    nonmanifold = [e for e in bm.edges if len(e.link_faces) > 2]   # T-junctions
    loose_verts = [v for v in bm.verts if not v.link_edges]
    loose_edges = [e for e in bm.edges if not e.link_faces]
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    volume = bm.calc_volume(signed=True)

    # Self-intersection: BVH overlap of the evaluated mesh against itself.
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(deps)
    tmp = bmesh.new()
    tmp.from_object(eval_obj, deps)
    tmp.transform(obj.matrix_world)
    tree = BVHTree.FromBMesh(tmp)
    overlaps = tree.overlap(tree)
    tmp.free()

    d = _world_bbox_dims(obj)
    report = {
        "faces": len(bm.faces),
        "tris": sum(len(f.verts) - 2 for f in bm.faces),
        "holes_boundary_edges": len(boundary),
        "nonmanifold_edges": len(nonmanifold),
        "loose_verts": len(loose_verts),
        "loose_edges": len(loose_edges),
        "ngons": len(ngons),
        "self_intersections": len(overlaps),
        "signed_volume_mm3": round(volume, 2),
        "normals_inverted": volume < 0,
        "dims_mm": (round(d[0], 2), round(d[1], 2), round(d[2], 2)),
        "min_z_mm": round(min((obj.matrix_world @ v.co).z for v in bm.verts), 2),
    }
    bm.free()

    report["watertight"] = (
        report["holes_boundary_edges"] == 0
        and report["nonmanifold_edges"] == 0
        and report["loose_verts"] == 0
    )
    report["print_ready"] = (
        report["watertight"]
        and not report["normals_inverted"]
        and report["self_intersections"] == 0
    )
    if verbose:
        for k, v in report.items():
            print(f"  {k}: {v}")
        print("  VERDICT:", "PRINT READY" if report["print_ready"] else "NOT READY")
    return report


# --------------------------------------------------------------------------
# Repair. Voxel remesh is the blunt instrument that reliably turns generated
# soup into a manifold solid. It destroys UVs and softens fine detail, so pick
# voxel_mm relative to the smallest feature you care about (roughly half of it).
# --------------------------------------------------------------------------
def repair(obj, voxel_mm=0.8, merge_mm=0.01):
    """Voxel Remesh needs input that already approximates a CLOSED volume to
    determine inside-vs-outside. Fed a wide-open single-surface shell (no
    back, no thickness yet — e.g. a face/mask surface before shell() has run),
    it doesn't degrade gracefully: it can silently reconstruct one small
    fragment where the surface happens to fold enough to look locally
    enclosed, and discard everything else. If your mesh is still an open
    shell rather than a closed-but-leaky scan/generator blob, run shell()
    BEFORE repair(), not after."""
    bpy.context.view_layer.objects.active = obj
    faces_before = len(obj.data.polygons)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_mm)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    m = obj.modifiers.new("PRINT-remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel_mm
    m.use_smooth_shade = False
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.update()

    faces_after = len(obj.data.polygons)
    print(f"repaired at {voxel_mm}mm voxel -> {faces_after:,} faces")

    if faces_before > 0 and faces_after < faces_before * 0.5:
        print(
            f"  WARNING: face count collapsed {faces_before:,} -> {faces_after:,} "
            f"({100 * (faces_after - faces_before) / faces_before:.1f}%). This usually "
            "means the input wasn't an approximately closed volume — Voxel Remesh "
            "reconstructed only a small enclosed fragment and discarded the rest. "
            "If this object is a bare open shell (no back/thickness), run shell() "
            "first, then repair() again on the result."
        )

    return obj


def decimate(obj, target_faces=200_000):
    """Voxel remesh can produce millions of faces. Slicers cope badly above
    ~500k and STL files get enormous."""
    current = len(obj.data.polygons)
    if current <= target_faces:
        print(f"decimate skipped ({current:,} faces)")
        return obj
    bpy.context.view_layer.objects.active = obj
    m = obj.modifiers.new("PRINT-decimate", "DECIMATE")
    m.ratio = target_faces / current
    bpy.ops.object.modifier_apply(modifier=m.name)
    print(f"decimated {current:,} -> {len(obj.data.polygons):,} faces")
    return obj


# --------------------------------------------------------------------------
# Scale and placement
# --------------------------------------------------------------------------
def scale_to_mm(obj, height_mm=None, width_mm=None, depth_mm=None):
    """Uniformly scale so one named axis matches a real measurement.
    Z = height, X = width, Y = depth. Adult face height is ~200-240mm.

    Measures against the true world-space bounding box, not obj.dimensions —
    obj.dimensions is local-space and silently targets the wrong axis if the
    object's rotation hasn't been baked down (e.g. it never went through
    import_mesh(), or was already sitting in the scene at an angle)."""
    d = _world_bbox_dims(obj)
    if height_mm:
        factor = height_mm / d[2]
    elif width_mm:
        factor = width_mm / d[0]
    elif depth_mm:
        factor = depth_mm / d[1]
    else:
        raise ValueError("give one of height_mm / width_mm / depth_mm")

    obj.scale = (obj.scale.x * factor, obj.scale.y * factor, obj.scale.z * factor)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    print(f"scaled x{factor:.4f} -> {tuple(round(v, 1) for v in _world_bbox_dims(obj))} mm (world)")
    return obj


def drop_to_bed(obj):
    """Sit the object on Z=0 so the slicer doesn't auto-shift it."""
    bpy.context.view_layer.update()
    lowest = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
    obj.location.z -= lowest
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True)
    print("dropped to Z=0")
    return obj


# --------------------------------------------------------------------------
# Hollowing
# --------------------------------------------------------------------------
def shell(obj, thickness_mm=2.5, open_back=True):
    """Turn a solid into a wearable shell.

    open_back removes faces whose normal points away from the viewer (+Y in
    world space), leaving an open cavity; Solidify then gives the remaining
    surface real thickness. 2.5mm is a sane minimum for a PLA/PETG wearable;
    go 3mm+ if it takes strap load. For resin, add drain holes afterwards or
    it will cup.
    """
    bpy.context.view_layer.objects.active = obj

    if open_back:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        # World-space normal: bm.from_mesh gives LOCAL normals, which silently
        # open the wrong side if the object's rotation hasn't been baked down
        # (same class of bug _world_bbox_dims fixes for measurements). Assumes
        # scale is already applied/uniform, true once scale_to_mm() has run.
        normal_mat = obj.matrix_world.to_3x3()
        back = [f for f in bm.faces if (normal_mat @ f.normal).y > 0.35]
        if back:
            bmesh.ops.delete(bm, geom=back, context="FACES")
            print(f"opened back: removed {len(back):,} faces")
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

    m = obj.modifiers.new("PRINT-solidify", "SOLIDIFY")
    m.thickness = thickness_mm
    m.offset = -1.0              # grow inward; preserves the outer silhouette
    m.use_even_offset = True
    m.use_rim = True
    m.use_rim_only = False
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.update()
    print(f"shelled at {thickness_mm}mm")
    return obj


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def export_stl(obj, path, ascii_format=False):
    """Scene units are mm and global_scale is 1, so the slicer reads real mm."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    kwargs = dict(filepath=path, export_selected_objects=True,
                  global_scale=1.0, ascii_format=ascii_format,
                  apply_modifiers=True)
    try:
        bpy.ops.wm.stl_export(**kwargs)          # Blender 4.2+ / 5.x
    except AttributeError:
        bpy.ops.export_mesh.stl(filepath=path, use_selection=True,
                                global_scale=1.0, ascii=ascii_format)
    import os
    print(f"exported {path} ({os.path.getsize(path):,} bytes), "
          f"dims {tuple(round(v, 1) for v in obj.dimensions)} mm")
    return path
