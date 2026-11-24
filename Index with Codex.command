#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  bash setup.command
fi
if ! command -v codex >/dev/null; then
  echo "Install and sign in to Codex CLI using your ChatGPT account first."
  echo "Then open Terminal in this folder and run: codex"
  exit 1
fi
exec codex "Index all pending learning materials according to AGENTS.md, including content-based material roadmaps. Use roadmap-pending and roadmap-context to fill missing roadmaps for previously indexed material without re-indexing concepts. Preserve evidence, existing modules, and completion state. Follow any imported study plan as written."
