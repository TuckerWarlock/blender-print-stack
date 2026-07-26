Vendored from RobLe3/cc-blender-skill (MIT), skill `contour-to-mesh`.

Local modifications:
- MCP tool names retargeted from the third-party `ahujasid/blender-mcp`
  naming (`mcp__blender__*`) to the official Blender Lab MCP server
  (`execute_blender_code`, `get_objects_summary`, `get_object_detail_summary`,
  `get_screenshot_of_window_as_image`, `render_viewport_to_path`).
- `evals/` removed.

Re-pull upstream with care: re-apply the tool renaming after any update.

Note: this SKILL.md references sibling skills from the upstream 30-skill set
that were deliberately NOT vendored (UV/texturing, atlas fitting, look
calibration, the harmonizer meta-layer). Those handoffs are inert here. They
concern texture and appearance work, which is irrelevant to geometry destined
for STL. Vendor them individually if you later need textured output.
