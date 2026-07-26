#!/usr/bin/env bash
# Install the blender-print-stack skills into ~/.claude/skills/
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$DEST"

echo "installing from $SRC -> $DEST"
for skill in "$SRC"/*/; do
  name="$(basename "$skill")"
  ln -sfn "$skill" "$DEST/$name"
  echo "  linked $name"
done

echo
echo "python deps:"
pip install -q -r "$(dirname "$SRC")/requirements.txt" && echo "  installed"

echo
echo "next:"
echo "  restart Claude Code to pick up the new skills"
