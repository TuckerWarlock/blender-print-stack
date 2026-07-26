# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A package of Claude Code **skills** for turning reference photos into a clean,
correctly scaled Blender mesh, verified against the source images. It sits on
top of two things it does not itself define:

1. The official **Blender Lab MCP server** (`blender_mcp/`, cloned in from
   `https://projects.blender.org/lab/blender_mcp.git`) — provides the
   `execute_blender_code`, `get_objects_summary`, `get_object_detail_summary`,
   `get_screenshot_of_window_as_image`, `render_viewport_to_path` tools that
   every skill calls.
2. Nine `skills/*/SKILL.md` skills, some new and some vendored/merged from
   third-party repos (`RobLe3/cc-blender-skill`, `Mik1703/blender-mcp-quality`,
   `ProfRino/Blender-MCP-Assembly-Skill`), documented in the table in
   README.md.

`blender_mcp/` is its own separate git checkout (has its own `.git`, own
remote, own history) — treat it as vendored upstream code, not something to
casually restructure. It is currently untracked in this repo's git status;
don't assume it should be committed without checking with the user first.

## Install / setup

```bash
chmod +x install.sh
./install.sh
```

This symlinks every `skills/*/` directory into `~/.claude/skills/` (or
`$CLAUDE_SKILLS_DIR` if set). Restart Claude Code after running it to pick up
new/changed skills.

Requires Blender 5.1+ with the official Blender MCP add-on
(`blender_mcp/addon/blender_mcp_addon/`) installed and running, connected via
`mcp.json` (`uv --directory ./blender_mcp/mcp run blender-mcp`).

Python deps (`requirements.txt`: opencv-python, numpy, scipy, Pillow) are
**optional** — only needed by the reference-comparison skills' local
render-vs-photo fitting scripts (not by anything running inside Blender). On
macOS, install them in a venv, not via bare `pip install` (PEP 668):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The Blender-side scripts (`mesh_repair.py`, `assembly_helpers.py`, etc.) run
inside Blender's bundled Python and need nothing from `requirements.txt`.

## Architecture

### Two build paths, chosen by subject type

- **Primitive assembly** (`blender-build-discipline`): for hard-surface /
  mechanical models built from primitives. Enforces connection planning before
  writing code, bmesh spans instead of rotated cylinders, transform hygiene,
  and a mandatory post-creation validation gate. Helper functions live in
  `scripts/assembly_helpers.py` — send that file through
  `execute_blender_code` once, then call its functions.
- **Organic / photo-reference modeling** (`face-mask-modeling`): the
  orchestrator for faces, masks, heads, busts, creatures. Explicitly *not*
  buildable from primitives — routes to whatever generator/scanner produced
  the mesh, then hands off to `blender-mesh-repair`, then the
  reference-comparison skills to verify against source photos.

These two paths are mutually exclusive per-subject: don't try to assemble an
organic subject from primitives, and don't route a hard-surface prop through
`face-mask-modeling`.

### The generator-agnostic pipeline (organic path)

```
photos ──> [ any generator/scanner ] ──> blender-mesh-repair ──> clean mesh
                                               ↑
                         orthographic-registration + multiview-fit-loop
                               (verify against the source photos)
```

This repo does not wrap any specific image-to-3D service. Whatever produced
the GLB/OBJ/PLY (TRELLIS.2, Hunyuan3D, photogrammetry, sculpting), it goes
through `blender-mesh-repair` in a fixed, non-optional order:

```python
setup_mm_units()                      # 1. BEFORE importing anything
obj = import_mesh("/abs/path.glb")    # 2. handles glTF parent nesting
# ... manifold repair, scale, decimate, hollow follow
```

Generated meshes arrive dense, non-manifold, and at arbitrary scale because
Apple Silicon MPS ports of image-to-3D models stub out CUDA-only
texture-baking/hole-filling — `blender-mesh-repair` exists specifically to fix
that. Generative output on a single frontal photo is *plausible, not
measured*: the back of the head is fiction unless multiple views were
supplied.

### Reference-comparison skills (the verification loop)

`orthographic-registration`, `multiview-fit-loop`, `reference-analysis-validator`,
`landmark-fit-repair`, `reference-to-3d`, `contour-to-mesh` — vendored from
`cc-blender-skill`, each a focused conceptual gate (40–220 lines) with backing
Python in `scripts/`, not a full modeling workflow on their own:

- `orthographic-registration` sets the shared coordinate contract: front view
  → X/Z silhouette, side view → Y/Z depth, top view → X/Y spread, back view →
  rear silhouette/material only (must not rewrite the front silhouette).
- `multiview-fit-loop` closes render → compare → adjust → re-render, checking
  bbox center/size, centroid drift, silhouette IoU, and visual overlay per
  view. Use when a model "still doesn't fit" the templates.
- `reference-analysis-validator` produces the measurable gate artifacts
  (`reference_manifest.json`, `source_analysis/*.json`,
  `validation/front_overlay_reference.png`,
  `validation/front_mask_validation.json`) — for brand/logo/mascot work, don't
  model or export until these exist.
- `landmark-fit-repair` turns named feature drift (eye line, jaw, leaf tip,
  aura ring, etc.) into recipe-parameter edits when bbox/IoU is too coarse.
- `contour-to-mesh` builds a mesh directly from a 2D silhouette/mask (front
  X/Z), adding depth only after the front-view boundary is validated.
- `reference-to-3d` is the source-locked reconstruction workflow: extract
  measurements/part counts/silhouettes from the reference *first*, then build
  to satisfy them — never generate a plausible object from memory and
  decorate it afterward.

### MCP tool naming — retarget after any upstream pull

Both vendored skill families were written against the third-party
`ahujasid/blender-mcp` server's tool names. Every vendored file here has been
retargeted to the official Blender Lab MCP names:

| Was (ahujasid) | Now (official) |
|---|---|
| `mcp__blender__execute_blender_code` | `execute_blender_code` |
| `mcp__blender__get_scene_info` | `get_objects_summary` |
| `mcp__blender__get_object_info` | `get_object_detail_summary` |
| `mcp__blender__get_viewport_screenshot` | `get_screenshot_of_window_as_image` |
| `mcp__blender__render_image` | `render_viewport_to_path` |

`download_polyhaven_asset` and `download_sketchfab_model` have no official
equivalent and nothing here depends on them. **If you re-pull any vendored
skill from upstream, you must re-apply this renaming** — each vendored
skill's `VENDORED.md` records exactly what was changed, use it as the diff
checklist.

### Skill file conventions

Every `skills/*/SKILL.md` has YAML frontmatter with `name`, `description`
(used for skill discovery/matching), and `when_to_use` (trigger phrasing).
Skills that call MCP tools directly also declare `allowed-tools`. Vendored
skills carry a sibling `VENDORED.md` documenting origin repo, license, and
local modifications — check it before touching a vendored skill.

## Working in `blender_mcp/`

`blender_mcp/` is a separate upstream project with its own Makefile:

```bash
cd blender_mcp
make test              # unit tests
make test_rst_parse    # RST manual/API doc parsing tests
make test_rst_search   # RST text-search layer tests
make test_integration TESTS=TestClass.test_name   # single integration test, needs BLENDER_BIN
make test_integration TESTS_LIST=1                # list all integration tests
make check_all         # ruff, mypy, vulture, license header, ascii, namespace checks
make format             # autopep8
```

Since this is vendored upstream, prefer not to make product changes here
unless the task is specifically about the MCP server/add-on itself — mismatch
with upstream makes future syncs harder.
