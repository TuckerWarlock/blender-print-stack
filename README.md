# blender-print-stack

Reference photos → a clean, correctly scaled Blender mesh, verified against the
source images.

Layers on top of your existing foundation (official Blender Lab MCP server +
ra100's eight `blender-skills:*` reference skills) rather than replacing it.

## Install

```bash
./install.sh
```

Requires Blender 5.1+ with the official Blender MCP add-on running. No API
keys, no subscriptions, no paid services.

## What's here

| Skill | Origin | Purpose |
|---|---|---|
| `face-mask-modeling` | new | Orchestrator: photos → clean mesh, generator-agnostic |
| `blender-mesh-repair` | new | mm units, manifold repair, scale, decimate, hollow |
| `blender-build-discipline` | merged | ProfRino assembly rules + Mik1703 validation gate |
| `orthographic-registration` | vendored | Reference planes at true scale |
| `multiview-fit-loop` | vendored | Render → compare → correct against source photos |
| `reference-analysis-validator` | vendored | IoU/SSIM/bbox overlay metrics |
| `landmark-fit-repair` | vendored | Named-feature correction (eye line, jaw, brow) |
| `reference-to-3d` | vendored | Source-locked reconstruction workflow |
| `contour-to-mesh` | vendored | Silhouette-derived mesh generation |

Nine skills, not thirty. The other twenty-plus from `cc-blender-skill` were left
out because they target hard-surface, logo, wireframe, animation, and lighting
work with no bearing on an organic subject. Add them individually if you start
doing props.

## Pipeline

```
photos ──> [ any generator/scanner ] ──> blender-mesh-repair ──> clean mesh
                                               ↑
                         orthographic-registration + multiview-fit-loop
                               (verify against the source photos)
```

## Deliberately generator-agnostic

This stack does not wrap any image-to-3D service. Get geometry however suits
the job, hand the GLB/OBJ/PLY to `blender-mesh-repair`, and everything
downstream works the same:

- **Open image-to-3D** — TRELLIS.2 (MIT) or Hunyuan3D 2.1 (Apache 2.0). Both
  have community MPS ports that run natively on Apple Silicon; free HuggingFace
  Spaces work in a browser as an alternative.
- **Photogrammetry** — if you have the physical object. Measures rather than
  invents. Apple Object Capture on macOS, or COLMAP cross-platform.
- **Sculpting** — reference photos as image planes, full control.

### Apple Silicon note

Run generators in a native venv, **not Docker**. macOS provides no Metal GPU
passthrough into containers, so a containerised model is CPU-only and not
viable for a 4B diffusion model. The MPS ports stub out the CUDA-only
texture-baking and hole-filling stages, which means meshes arrive with holes
and at full density — precisely what `blender-mesh-repair` exists to fix.

Generative output is *plausible*, not measured: these models invent geometry
they cannot see. On a single frontal photo the back of the head is fiction.
Supply multiple views where the generator accepts them.

## Note on the reference-comparison skills

The `reference-*` family from `cc-blender-skill` is 40–220 lines each — useful
conceptual gates with backing Python, not deep workflows. They earn their place
as the verification loop, not as the thing that builds the model.

## MCP tool naming

Both `cc-blender-skill` and `blender-mcp-quality` were written against the
third-party `ahujasid/blender-mcp` server. All vendored files have been
retargeted to the official Blender Lab names:

| Was | Now |
|---|---|
| `mcp__blender__execute_blender_code` | `execute_blender_code` |
| `mcp__blender__get_scene_info` | `get_objects_summary` |
| `mcp__blender__get_object_info` | `get_object_detail_summary` |
| `mcp__blender__get_viewport_screenshot` | `get_screenshot_of_window_as_image` |
| `mcp__blender__render_image` | `render_viewport_to_path` |

`download_polyhaven_asset` and `download_sketchfab_model` exist only on the
ahujasid server and have no official equivalent — nothing here depends on them.

Re-apply this renaming after pulling any upstream update. Each vendored skill
carries a `VENDORED.md` recording what was changed.

## Not tested

The Blender-side scripts need a real Blender session; they are syntax-clean but
unexercised. The `shell(open_back=True)` heuristic in particular assumes the
subject faces -Y and will cut the wrong side on a rotated import — check before
applying Solidify.

## Licences

All upstream sources are MIT: `RobLe3/cc-blender-skill`,
`Mik1703/blender-mcp-quality`, `ProfRino/Blender-MCP-Assembly-Skill`.
`seehiong/blender-mcp-n8n` was evaluated and not used — it is an n8n-oriented
MCP server with a fixed architectural/MEP tool surface, which is both the wrong
client and a less capable interface than raw `execute_blender_code`.
