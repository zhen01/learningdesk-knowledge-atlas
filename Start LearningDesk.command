#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  bash setup.command
fi
exec .venv/bin/python atlas.py serve
