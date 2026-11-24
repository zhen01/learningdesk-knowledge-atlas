#!/usr/bin/env python3
"""Install only LearningDesk source files into an existing local installation."""
import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
CODE = (
    "atlas.py", "AGENTS.md", "README.md", "LICENSE", ".gitignore",
    "requirements.txt", "requirements-dev.txt", "setup.command",
    "Start LearningDesk.command", "Index with Codex.command", "update_existing.py",
    "test_atlas.py", "web/index.html", "web/app.js", "web/style.css",
    "web/reader.js", "web/graph.js", "web/upgrade.css",
)

def update(destination, source=SOURCE):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("Use the downloaded new version as source and your existing installation as destination.")
    if not (destination / "atlas.py").is_file():
        raise ValueError("Destination does not look like an existing LearningDesk installation.")
    for name in CODE:
        if not (source / name).is_file():
            raise ValueError(f"New version is missing {name}; no files were changed.")
        target = destination / name
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != destination and destination in p.parents):
            raise ValueError(f"Refusing to overwrite a symlink: {name}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = destination / "data" / "backups" / f"before-code-update-{timestamp}.sqlite"
    database = destination / "data" / "atlas.sqlite"
    if database.is_file():
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as old, sqlite3.connect(backup) as new:
            old.backup(new)
    for name in CODE:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    return backup if database.is_file() else None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("existing_folder", type=Path)
    args = parser.parse_args()
    snapshot = update(args.existing_folder)
    print("Updated application source only. Existing documents, database, inbox and virtual environment were preserved.")
    if snapshot:
        print(f"Database backup: {snapshot}")
