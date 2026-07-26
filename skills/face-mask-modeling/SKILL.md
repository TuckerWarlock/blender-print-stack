---
name: face-mask-modeling
description: Turn reference photographs of a face, mask, head, bust, or creature into a clean, correctly scaled Blender mesh. Use when the user supplies photos of an organic or sculpted subject and wants a usable model out of Blender. Generator-agnostic — works with any imported mesh regardless of where it came from.
when_to_use: Reference photos of a face/mask/head/bust/creature, "model this from these pictures", cleaning up a generated or scanned mesh, matching a model to source photographs.
---

# Face / Mask Photos → Clean Blender Mesh

## Read this before starting

Organic subjects cannot be built from primitives. Do not route a face or mask
through primitive assembly — a sphere with a nose and brows reads as "abstract
avatar," never as a face. The workable paths are generation, scanning, or
sculpting; this skill covers everything that happens *after* you have geometry,
plus verifying it against the source photos.

## Pipeline

```
reference photos
   ↓  [ get geometry — see options below, external to this stack ]
   ↓  blender-mesh-repair        import → diagnose → repair → scale
   ↓  orthographic-registration  reference planes at true scale
   ↓  multiview-fit-loop         render vs photo, measure drift, correct
   ↓  landmark-fit-repair        fix named features (eye line, jaw, brow)
   ↓  blender-mesh-repair        final diagnose → hollow if needed → export
```

## Step 1 — Get geometry

This stack deliberately does not wrap any one generator. Pick whichever fits
the job and hand the resulting GLB/OBJ/PLY to `blender-mesh-repair`.

| Situation | Option |
|---|---|
| Only have photos/artwork | Open image-to-3D: **TRELLIS.2** (MIT) or **Hunyuan3D 2.1** (Apache 2.0). Runs locally on Apple Silicon via the MPS ports — see below. Free HuggingFace Spaces also work in a browser if you'd rather not install. |
| Have the physical mask in hand | Photogrammetry beats generation, and it *measures* rather than invents. On macOS, Apple's Object Capture (via a front-end app) works from a ring of photos. COLMAP is the cross-platform open option. |
| Want full control / it's a stylised design | Sculpt in Blender with the reference photos as image planes. Slower, but the only path that gives exact intent. |
| Need it to match a real person's likeness | Generation will produce "a face," not "their face." Scan or sculpt. |

### Running locally on Apple Silicon

Do **not** try this in Docker. macOS has no Metal GPU passthrough into
containers — Docker's own Metal inference backend runs natively on the host for
exactly this reason. A container gets you CPU-only, which is not viable for a
4B diffusion model. Use a native venv.

Community MPS ports replace the CUDA-only pieces (flash_attn, nvdiffrast,
sparse 3D conv, cumesh) with pure-PyTorch equivalents:

- **TRELLIS.2** — MPS port generates ~400K-vertex meshes in roughly 3.5 min at
  512³ on an M4 with 24GB, peaking near 18GB.
- **Hunyuan3D 2.1** — `Brainkeys/Hunyuan3D-2.1-mac` fork ships MPS support.

Two consequences that matter here:

1. **Texture baking is stubbed out** (nvdiffrast is CUDA-only). Output is
   vertex colours, not UV textures. Irrelevant for geometry work.
2. **Hole-filling and decimation are stubbed out** (cumesh is CUDA-only), so
   meshes arrive with holes and full density. This is exactly what
   `blender-mesh-repair` fixes — `repair()` closes the holes via voxel remesh
   and `decimate()` handles the density. The port's biggest weakness is this
   stack's job.

Peak memory near 18GB on a 24GB machine is tight: quit other applications
first. On a fanless Air, expect longer than the quoted times and thermal
throttling across back-to-back runs — generate in small batches.

**Generative output is plausible, not measured.** These models invent geometry
they cannot see — on a single frontal photo, the entire back of the head is
fiction. Supply front, both three-quarters, and profile views where the
generator accepts multiple images.

Generate two or three variants before investing cleanup effort in one. Picking
the best of three costs less than repairing the worst.

## Step 2 — Triage before cleanup

- **Solid or wearable?** A display bust is solid. A wearable mask needs a
  shell, an open back, and eye/mouth apertures.
- **Target size?** Needed for `scale_to_mm`. An adult wearable face mask is
  roughly 200–240mm tall.
- **Sculpt further, or use as-is?** Changes the remesh strategy — Quadriflow
  for editable topology, Voxel for a watertight solid.

## Step 3 — Clean and scale

Delegate to `blender-mesh-repair`. The ordering constraints there are real:
units before import, scale before shelling. Read that skill's ordering section
rather than improvising.

For a face at 200–240mm, `voxel_mm` of 0.6–1.0 keeps wrinkles and skin
texture; above 2.0 the features go soft.

## Step 4 — Verify against the source

The step people skip. Use `orthographic-registration` to place the reference
photos as image planes at the model's true scale, then `multiview-fit-loop` to
render silhouettes and measure drift. `landmark-fit-repair` handles named
features when the overall silhouette passes but the eye line or jaw is visibly
wrong.

For a wearable, also check interior clearance: measure inside width at temple
height. Under ~150mm and nobody is wearing it.

## Step 5 — Hand off

Report final dimensions in mm, wall thickness if shelled, triangle count, and
anything still outstanding. The user handles export and slicing.

## Honest limits

- Detail below the voxel size is gone after repair and unrecoverable. Regenerate
  at higher quality rather than trying to rescue it.
- Undercuts that look fine on screen may need supports or splitting.
- A mesh that passes `diagnose()` can still be unusable for reasons this stack
  does not check: floating islands, zero-area slivers, features below the
  nozzle width. The slicer's own preview is the final word.
