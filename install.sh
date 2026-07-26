#!/usr/bin/env bash
# Install the blender-print-stack skills into ~/.claude/skills/
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"

echo "installing from $SRC -> $DEST"
for skill in "$SRC"/*/; do
  name="$(basename "$skill")"
  ln -sfn "$skill" "$DEST/$name"
  echo "  linked $name"
done

cat <<'NOTE'

Python deps are OPTIONAL. They are needed only by the reference-comparison
skills (orthographic-registration, multiview-fit-loop,
reference-analysis-validator, landmark-fit-repair, reference-to-3d,
contour-to-mesh) when you run their render-vs-photo fitting scripts.

The Blender-side scripts (mesh_repair.py, assembly_helpers.py) run inside
Blender's bundled Python and need nothing installed.

To install them when you need them, in a venv (recommended on macOS, where a
bare `pip install` is blocked by PEP 668):

  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt

Or with uv:

  uv venv && uv pip install -r requirements.txt

NOTE

echo "next: restart Claude Code to pick up the new skills"
