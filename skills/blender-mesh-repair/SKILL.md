---
name: blender-mesh-repair
description: Make an imported, generated, or scanned mesh usable in Blender — millimetre units, manifold repair, real-world scaling, decimation, and optional hollowing. Use whenever a mesh arrives from outside Blender (GLB/OBJ/PLY from an image-to-3D model, a photogrammetry scan, or a downloaded asset) and is non-manifold, wrongly scaled, or inside out.
when_to_use: Imported mesh is broken, non-manifold, holes, inverted normals, wrong scale, self-intersecting, too dense, remesh, decimate, hollow, watertight, glTF import problems.
---

# Mesh Repair & Scaling

Meshes from image-to-3D generators, photogrammetry, and asset libraries arrive
as dense unstructured triangle soup with inconsistent normals and no real-world
scale. This skill makes them into something you can actually work with.

## Loading the helpers

`execute_blender_code` does **not** retain a Python namespace between calls —
each call gets a fresh global scope, so definitions sent in one call are gone by
the next. Prefix every call that uses these helpers with:

```python
import os
exec(open(os.path.expanduser(
    "~/.claude/skills/blender-mesh-repair/scripts/mesh_repair.py")).read())
```

One line, works regardless of interpreter state, and the path is stable because
`install.sh` symlinks the skill there.

If you are working in Blender's Scripting workspace instead of over MCP, the
namespace does persist and you can run the module once.

## The order is not optional

```python
setup_mm_units()                      # 1. BEFORE importing anything
obj = import_mesh("/abs/path.glb")    # 2. handles glTF parent nesting
diagnose(obj)                         # 3. know your starting state
scale_to_mm(obj, height_mm=240)       # 4. REAL SIZE FIRST
obj = repair(obj, voxel_mm=0.8)       # 5. now voxel_mm means something
obj = shell(obj, thickness_mm=2.5)    # 6. wearables/hollow only
decimate(obj, target_faces=300_000)   # 7. if needed
diagnose(obj)                         # 8. confirm clean
```

Three ordering traps. All three come from the same root cause: `voxel_mm` and
`thickness_mm` are **absolute** sizes, so they only mean anything once the mesh
is at real-world scale.

- **Units before import.** Setting scene units afterwards changes what the
  numbers mean but not the geometry, and every later measurement lies.
- **Scale before repair.** Imported meshes arrive at arbitrary scale, often
  1–2 units tall. Remeshing a 2mm object at `voxel_mm=0.8` gives you two voxels
  across and destroys it — and the result still reports `watertight: True`,
  because a lumpy 60-triangle blob is a valid closed manifold. Always check the
  face count after `repair()`: if it dropped by orders of magnitude, you
  remeshed before scaling.
- **Scale before shell.** Shell at 2.5mm then scale 10x and you have a 25mm
  wall.

## `repair()` needs an approximately closed volume

The order above (`repair()` then optional `shell()`) assumes the input is
already close to a solid — the normal case for scans/generator output, which
arrive dense and leaky but roughly volumetric. **If the mesh is instead a bare
open shell — a single surface with no back and no thickness yet (built
directly as a face/mask surface, or any import that's missing a side) —
`shell()` must run BEFORE `repair()`, not after.**

Voxel Remesh needs to determine inside-vs-outside to reconstruct a solid. Fed
a wide-open single-surface sheet, it doesn't error — it silently reconstructs
whatever small region happens to fold enough to look locally enclosed and
discards the rest. This can look like a normal, if aggressive, cleanup (still
reports `watertight: True`, still runs without error) while actually having
thrown away 90%+ of the mesh. `repair()` now prints a loud warning to stdout
whenever face count drops by more than half, precisely to catch this — but
the real fix is running `shell()` first for any mesh that's still an open
shell. Check `diagnose()`'s `holes_boundary_edges` beforehand: a small handful
of scattered boundary edges is a normal leaky scan; one or more large
boundary loops spanning most of the object's own size means it's an open
shell, not a closed-but-leaky blob.

## Measurements are rotation-safe, but only because of that

`diagnose()`'s `dims_mm` and `scale_to_mm()`'s height/width/depth targeting
read the object's **true world-space bounding box** (computed from actual
vertex world coordinates), not `obj.dimensions`. That distinction matters:
`obj.dimensions` is a local-space measurement — it does not rotate into world
space — so on any object whose rotation hasn't been baked down (skipped
`import_mesh()`, appended from another file, already sitting in the scene at
an angle) it silently reports the wrong axis as "height." A mesh rotated ~90°
about X will have its real-world Y and Z sizes swapped in `obj.dimensions`
with no error or warning.

`import_mesh()` avoids this by baking rotation down via
`clear_parents_and_apply()` on the way in. If you're diagnosing/scaling an
object that entered the scene some other way, check `obj.rotation_euler` isn't
sitting on a non-zero value before trusting a *visual* sense of "up" — the
numbers from `diagnose()`/`scale_to_mm()` are correct either way, but Blender's
own `obj.dimensions` (if you're spot-checking in the Properties panel or a
one-off script) is not.

## Why millimetres

`setup_mm_units()` sets `scale_length = 0.001` so 1 Blender unit = 1 mm. Most
downstream formats — STL above all — are unitless and consumers assume mm.
Working in mm from the start means the numbers you read in Blender are the
numbers everything else sees, with no conversion in your head.

## Import

Use `import_mesh()` rather than a bare `bpy.ops.import_scene.gltf`. glTF nests
meshes under rotated parent empties, so `obj.dimensions` and all bounds
measurements read wrong until parents are cleared and transforms applied.
`import_mesh()` does that, joins multi-part imports, and drops the generated
materials.

## Reading `diagnose()`

| Field | Meaning | Fix |
|---|---|---|
| `holes_boundary_edges` | Edges with one face — mesh is open | `repair()`, or intentional on an open shell |
| `nonmanifold_edges` | Edges with 3+ faces — impossible solid | `repair()` |
| `normals_inverted` | Signed volume negative — inside out | `repair()` recalculates |
| `self_intersections` | Geometry passing through itself | `repair()`; if it survives, the source is bad |
| `loose_verts` / `loose_edges` | Stray geometry | `repair()` |
| `dims_mm` | Real size — sanity-check it | `scale_to_mm()` |
| `watertight` | Closed, manifold, no strays | prerequisite for booleans and solid export |

## Choosing `voxel_mm`

Voxel remesh is the blunt instrument that reliably makes generated soup
manifold. It discards UVs and softens detail, so size it against the smallest
feature worth keeping — roughly half of it.

| Subject | voxel_mm | Note |
|---|---|---|
| Face/mask at 200–240mm | 0.6–1.0 | Keeps wrinkles and skin texture |
| Same, above 2.0 | — | Features go soft and mushy |
| Chunky prop | 1.5–2.5 | Fewer faces, faster |
| Fine detail work | 0.2–0.4 | Face count explodes; decimate after |

Remesh output is frequently in the millions of faces — `decimate()` afterwards.

**If the mesh will be sculpted further, use Quadriflow instead of Voxel.**
Voxel gives a watertight solid with unusable edge flow; Quadriflow gives quads
you can actually work with.

## Hollowing

`shell()` is for wearables and weight reduction. `open_back=True` removes faces
whose *world-space* normal points backwards (+Y), then Solidify gives the
remaining surface thickness with `offset = -1.0` so it grows inward and the
outer silhouette is preserved.

The +Y heuristic assumes the subject faces -Y **in world space**. It checks
`obj.matrix_world.to_3x3() @ f.normal`, not the raw local-space normal, so an
object whose rotation hasn't been baked down is still handled correctly (same
fix as `diagnose()`/`scale_to_mm()` — see above). It does still assume `obj`'s
scale is already uniform/applied, which is true once `scale_to_mm()` has run
per the documented order. Verified directly: on a closed test sphere, `shell()`
opened the +Y hemisphere and left -Y intact, confirmed by rendering both
sides. Still worth a look at the face-deletion print (`opened back: removed N
faces`) before trusting the result blind — a broad, gently-curved subject can
have more or less of its rim caught by the 0.35 threshold than expected.

Rough wall thickness guidance: 2.0–2.5mm for a decorative shell, 3mm+ if it
takes strap or handling load. Adjust to your own process and material.

## Verify against a reference

If the mesh needs to match source photographs, `orthographic-registration` and
`multiview-fit-loop` handle the render-compare-correct loop. Scale first — the
comparison is meaningless against a mesh at arbitrary size.

## Export

`export_stl()` is included as a convenience: scene units are mm and
`global_scale` is 1.0, so the file carries honest millimetres and needs no
rescaling downstream. It handles both the 4.2+/5.x `wm.stl_export` and the
legacy `export_mesh.stl` operator.

Any other format is fine too — the point of this skill is the mesh being clean
and correctly scaled before it leaves Blender.
