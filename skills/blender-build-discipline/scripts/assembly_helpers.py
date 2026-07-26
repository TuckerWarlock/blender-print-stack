"""
Build-discipline helpers: assembly verification + a post-creation validation gate.

Consolidated from two MIT-licensed sources, adapted to millimetre-first scenes
and the official Blender Lab MCP server:
  - ProfRino/Blender-MCP-Assembly-Skill  — connection planning, bounds/overlap
    verification, beam construction, transform auditing
  - Mik1703/blender-mcp-quality          — post-creation validation gate,
    Blender 5.1 API correctness, spatial checks

Run inside Blender via `execute_blender_code`.
"""

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def make_beam(name, start, end, half_w=0.012, half_h=0.010):
    """Build a box spanning start->end directly in bmesh.

    Never rotate a cylinder with Euler angles to point it at something: the
    result depends on rotation order and silently goes wrong for any direction
    that is not axis-aligned. Constructing the geometry along the actual vector
    has no such failure mode.
    """
    start, end = Vector(start), Vector(end)
    axis = end - start
    length = axis.length
    if length == 0:
        raise ValueError(f"{name}: start and end are identical")
    d = axis.normalized()

    # Build an orthonormal frame around the span direction.
    up = Vector((0, 0, 1))
    if abs(d.dot(up)) > 0.999:
        up = Vector((0, 1, 0))
    side = d.cross(up).normalized()
    up = side.cross(d).normalized()

    bm = bmesh.new()
    for t in (0.0, length):
        centre = start + d * t
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            bm.verts.new(centre + side * (sx * half_w) + up * (sy * half_h))
    bm.verts.ensure_lookup_table()
    v = bm.verts
    for quad in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                 (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
        bm.faces.new([v[i] for i in quad])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)   # unlinked objects are invisible
    return obj


# --------------------------------------------------------------------------
# Verification — call after every part, not at the end
# --------------------------------------------------------------------------
def verify_bounds(name, quiet=False):
    """World-space bounding box of a named object."""
    obj = bpy.data.objects[name]
    bpy.context.view_layer.update()          # stale depsgraph = wrong numbers
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    b = {
        "x": (min(v.x for v in vs), max(v.x for v in vs)),
        "y": (min(v.y for v in vs), max(v.y for v in vs)),
        "z": (min(v.z for v in vs), max(v.z for v in vs)),
    }
    if not quiet:
        print(f"{name}: "
              f"X[{b['x'][0]:.3f},{b['x'][1]:.3f}] "
              f"Y[{b['y'][0]:.3f},{b['y'][1]:.3f}] "
              f"Z[{b['z'][0]:.3f},{b['z'][1]:.3f}]")
    return b


def verify_overlap(name_a, name_b, axis="z", min_overlap=0.005):
    """Confirm two parts physically intersect on an axis. Run this for every
    joint in the connection map before moving on."""
    a = verify_bounds(name_a, quiet=True)
    b = verify_bounds(name_b, quiet=True)
    overlap = min(a[axis][1], b[axis][1]) - max(a[axis][0], b[axis][0])
    ok = overlap >= min_overlap
    print(f"  {name_a} <-> {name_b} [{axis.upper()}]: "
          f"{'OK' if ok else 'GAP'} ({overlap:.4f})")
    return overlap


def check_contact(name_a, name_b, max_gap=0.02):
    """Nearest-vertex distance between two objects. Catches parts that are
    close but not touching, which bounds-overlap alone can miss."""
    a, b = bpy.data.objects[name_a], bpy.data.objects[name_b]
    bpy.context.view_layer.update()
    va = [a.matrix_world @ v.co for v in a.data.vertices]
    vb = [b.matrix_world @ v.co for v in b.data.vertices]
    nearest = min((p - q).length for p in va for q in vb)
    ok = nearest <= max_gap
    print(f"  {name_a} <-> {name_b}: {'CONTACT' if ok else 'FLOATING'} "
          f"(gap {nearest:.4f})")
    return nearest


# --------------------------------------------------------------------------
# Finalisation
# --------------------------------------------------------------------------
def finalize(name, smooth=True):
    """Apply transforms, centre the origin, optionally shade smooth."""
    obj = bpy.data.objects[name]
    bpy.ops.object.select_all(action="DESELECT")   # scope ops to this object
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="MEDIAN")
    if smooth:
        bpy.ops.object.shade_smooth()
    bpy.ops.object.select_all(action="DESELECT")
    return obj


def audit_all():
    """Every mesh should end at rotation (0,0,0) and scale (1,1,1). Anything
    else means an unapplied transform is waiting to corrupt a later boolean,
    modifier, or export."""
    meshes = sorted((o for o in bpy.data.objects if o.type == "MESH"),
                    key=lambda o: o.name)
    all_ok = True
    for obj in meshes:
        rot = tuple(round(c, 3) for c in obj.rotation_euler)
        scl = tuple(round(c, 3) for c in obj.scale)
        ok = rot == (0.0, 0.0, 0.0) and scl == (1.0, 1.0, 1.0)
        all_ok &= ok
        print(f"  [{'OK' if ok else '!!'}] {obj.name:30s} rot={rot} scl={scl}")
    print(f"\nAll transforms clean: {bool(all_ok)}")
    return bool(all_ok)


# --------------------------------------------------------------------------
# Validation gate — run before declaring any model finished
# --------------------------------------------------------------------------
def validate_scene(poly_budget=None, ground_z=0.0, ignore_related=True):
    """Scene-wide check: poly count, degenerate geometry, ground placement,
    and unexpected object intersections.

    ignore_related suppresses overlaps between parented objects, which are
    expected in rigged assemblies and would otherwise drown the real errors.
    """
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    issues = []

    total = sum(len(o.data.polygons) for o in meshes)
    print(f"objects: {len(meshes)}   faces: {total:,}")
    if poly_budget and total > poly_budget:
        issues.append(f"poly budget exceeded: {total:,} > {poly_budget:,}")

    trees = {}
    for o in meshes:
        if not o.data.vertices:
            issues.append(f"{o.name}: empty mesh")
            continue

        bm = bmesh.new()
        bm.from_mesh(o.data)
        loose = [v for v in bm.verts if not v.link_edges]
        nonman = [e for e in bm.edges if len(e.link_faces) > 2]
        if loose:
            issues.append(f"{o.name}: {len(loose)} loose verts")
        if nonman:
            issues.append(f"{o.name}: {len(nonman)} non-manifold edges")
        bm.free()

        lo = min((o.matrix_world @ v.co).z for v in o.data.vertices)
        if lo < ground_z - 1e-4:
            issues.append(f"{o.name}: {ground_z - lo:.4f} below ground")

        tmp = bmesh.new()
        tmp.from_object(o.evaluated_get(deps), deps)
        tmp.transform(o.matrix_world)
        trees[o.name] = (BVHTree.FromBMesh(tmp), o)
        tmp.free()

    names = list(trees)
    for i, na in enumerate(names):
        for nb in names[i + 1:]:
            ta, oa = trees[na]
            tb, ob = trees[nb]
            if ignore_related and (oa.parent is ob or ob.parent is oa
                                   or (oa.parent and oa.parent is ob.parent)):
                continue
            if ta.overlap(tb):
                issues.append(f"{na} intersects {nb}")

    if issues:
        print(f"\n{len(issues)} ISSUE(S):")
        for it in issues:
            print(f"  - {it}")
    else:
        print("\nvalidation passed")
    return issues
