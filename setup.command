#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Install Python 3 from https://www.python.org/downloads/macos/ and run this again."
  exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
echo "LearningDesk is ready. Open Start LearningDesk.command."
