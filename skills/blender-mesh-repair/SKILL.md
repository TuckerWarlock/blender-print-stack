---
name: blender-mesh-repair
description: Make an imported, generated, or scanned mesh usable in Blender — millimetre units, manifold repair, real-world scaling, decimation, and optional hollowing. Use whenever a mesh arrives from outside Blender (GLB/OBJ/PLY from an image-to-3D model, a photogrammetry scan, or a downloaded asset) and is non-manifold, wrongly scaled, or inside out.
when_to_use: Imported mesh is broken, non-manifold, holes, inverted normals, wrong scale, self-intersecting, too dense, remesh, decimate, hollow, watertight, glTF import problems.
---

# Mesh Repair & Scaling

Meshes from image-to-3D generators, photogrammetry, and asset libraries arrive
as dense unstructured triangle soup with inconsistent normals and no real-world
scale. This skill makes them into something you can actually work with.

Helpers live in `scripts/mesh_repair.py`. Send it through
`execute_blender_code`, then call the functions.

## The order is not optional

```python
setup_mm_units()                      # 1. BEFORE importing anything
obj = import_mesh("/abs/path.glb")    # 2. handles glTF parent nesting
diagnose(obj)                         # 3. know your starting state
obj = repair(obj, voxel_mm=0.8)       # 4. remesh to manifold
scale_to_mm(obj, height_mm=240)       # 5. real size BEFORE shelling
obj = shell(obj, thickness_mm=2.5)    # 6. wearables/hollow only
decimate(obj, target_faces=300_000)   # 7. if needed
diagnose(obj)                         # 8. confirm clean
```

Two ordering traps:

- **Units before import.** Setting scene units afterwards changes what the
  numbers mean but not the geometry, and every later measurement lies.
- **Scale before shell.** Solidify thickness is absolute. Shell at 2.5mm then
  scale 10x and you have a 25mm wall.

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
whose normal points backwards (+Y), then Solidify gives the remaining surface
thickness with `offset = -1.0` so it grows inward and the outer silhouette is
preserved.

The +Y heuristic assumes the subject faces -Y. **Check the orientation before
shelling** — on a rotated import it will open the wrong side. Look at the
result of the face-deletion step before applying Solidify.

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
