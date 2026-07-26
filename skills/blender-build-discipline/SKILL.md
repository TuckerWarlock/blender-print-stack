---
name: blender-build-discipline
description: Assembly and validation rules for building models in Blender via MCP — connection planning, correct primitive scaling, bmesh spans instead of rotated cylinders, transform hygiene, and a mandatory post-creation validation gate. Use whenever constructing geometry from primitives, and before declaring any model finished.
when_to_use: Building models from primitives, parts not connecting, floating or exploded geometry, objects below ground, wrong scale, poly count blowout, validating a finished model, Blender 5.1 API errors.
---

# Blender Build Discipline

Consolidates the assembly rules from `ProfRino/Blender-MCP-Assembly-Skill` with
the validation gate from `Mik1703/blender-mcp-quality`, retargeted to the
official Blender Lab MCP server (`execute_blender_code`, `get_objects_summary`).

Helpers live in `scripts/assembly_helpers.py`. `execute_blender_code` does not
retain a Python namespace between calls, so prefix every call that uses them:

```python
import os
exec(open(os.path.expanduser(
    "~/.claude/skills/blender-build-discipline/scripts/assembly_helpers.py")).read())
```

**Scope note:** this is for models assembled from primitives. Organic subjects
(faces, masks, creatures) cannot be built this way — route those to
`face-mask-modeling` instead.

## Phase 1 — Plan connections before writing any code

Write the connection map first. For each joint state: which two parts, which
faces touch, and the minimum overlap. Models come out "exploded" because the
assembly logic was never made explicit, not because the maths was hard.

```
seat_top  <-> leg_fl : leg top face into seat underside, overlap >= 5mm
backrest  <-> seat   : backrest base into seat rear, overlap >= 8mm
```

## Phase 2 — Construction rules

**Use `size=2` for cube primitives.** With `size=2` the default cube spans -1..1,
so `scale` reads directly as the half-extent. With `size=1` every scale value
means half what it appears to, which is the single most common source of
parts at double or half their intended size.

```python
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0.4))
bpy.context.object.scale = (0.2, 0.2, 0.02)   # -> 400 x 400 x 40mm
```

**Never Euler-rotate a cylinder to span between two points.** The result
depends on rotation order and silently breaks for non-axis-aligned directions.
Use `make_beam(name, start, end)`, which constructs the geometry along the
actual vector.

**Apply transforms immediately after scaling**, especially inside loops.
Deferred transforms get applied to the wrong active object surprisingly often.

**Derive dimensions from verified neighbours.** Measure with `verify_bounds()`
and size the new part from the result rather than from an independent guess.

**Link every new object to a collection.** Objects created via `bpy.data` are
invisible and unrenderable until linked — a frequent silent failure.

## Phase 3 — Verify after every part

```python
verify_bounds("leg_fl")
verify_overlap("seat_top", "leg_fl", axis="z", min_overlap=0.005)
check_contact("seat_top", "leg_fl", max_gap=0.02)
```

Run `verify_overlap` for **every joint in the connection map** before moving to
the next part. Catching a gap immediately costs one correction; catching it at
the end costs a rebuild.

`verify_overlap` uses bounding boxes and can report overlap for parts that are
diagonally offset. `check_contact` measures nearest-vertex distance and catches
those. Use both on joints that matter.

## Phase 4 — Finalize and audit

```python
for name in part_names:
    finalize(name)
audit_all()
```

`audit_all()` must report clean. Every mesh should end at rotation `(0,0,0)`
and scale `(1,1,1)` — anything else is an unapplied transform waiting to
corrupt a later boolean, modifier, or export.

## Phase 5 — Validation gate

```python
validate_scene(poly_budget=200_000, ground_z=0.0)
```

Checks poly budget, empty meshes, loose vertices, non-manifold edges,
below-ground placement, and unexpected intersections. Do not tell the user a
model is finished until this returns no issues, or until each remaining issue
is explained and justified.

Parent-child overlap (wheels on an axle, a rig inside a mesh) is expected and
suppressed by `ignore_related=True`. Turn it off only when auditing a scene
that should have no touching parts at all.

## Blender 5.x API correctness

These are the errors that recur most:

| Wrong | Right |
|---|---|
| `mesh.calc_normals()` | Removed in 4.x. Normals are automatic; use `bmesh.ops.recalc_face_normals` to fix orientation |
| `BLENDER_EEVEE_NEXT` | `BLENDER_EEVEE` in 5.x |
| `mat.use_nodes = True` | No-op in 5.1; the node tree already exists after `materials.new()` |
| Reading `mesh.vertices` in Edit Mode | Out of sync. Use `bmesh.from_edit_mesh()`, or leave Edit Mode first |
| `BVHTree.FromObject(obj)` without depsgraph | Requires an evaluated depsgraph or modifiers are ignored |
| Measuring right after a transform | Call `bpy.context.view_layer.update()` first or you read stale values |
| Direct `Action.fcurves` for animation | 5.1 uses slotted actions: Action → Layer → Strip → Channelbag → FCurves |
| Python `threading` for bpy work | Unsupported. Use timers or the main-thread queue |
| Operators for bulk data changes | Prefer direct `bpy.data` access; operators depend on context and are slow |

Confirm any uncertain API name with `search_api_docs` before calling it rather
than guessing — a wrong enum fails loudly, a wrong property fails silently.

## Poly budgets

Generated and subdivided geometry blows up fast. Rough ceilings before things
get unwieldy:

| Use | Budget |
|---|---|
| Background/simple prop | 5k |
| Hero prop | 20–50k |
| Character | 50–150k |
| Print-destined mesh | up to 500k, then decimate |

A UV sphere at 128 segments is 16,000 faces on its own. Default to 32 segments
and raise it only where the silhouette actually needs it.

## Single-step discipline

Make one change per `execute_blender_code` call, then inspect. Batching ten
operations into one call means a failure at step three leaves the scene in an
unknown state that is far more expensive to diagnose than the round trips saved.
