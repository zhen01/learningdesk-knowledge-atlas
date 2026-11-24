#!/bin/bash
set -e
cd "$(dirname "$0")"
existing="$(pwd -P)"
temp="$(mktemp -d)"
trap 'rm -rf -- "$temp"' EXIT
git clone --depth 1 https://github.com/zhen01/learningdesk-knowledge-atlas.git "$temp/source"
python3 "$temp/source/update_existing.py" "$existing"
echo "Update complete. Restart LearningDesk from this same folder."
