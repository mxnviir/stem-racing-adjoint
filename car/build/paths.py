"""The repo's folders on sys.path (repo_paths.py at the root); PARTS names the car's folders."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import repo_paths  # noqa: E402

PARTS = {k: repo_paths.FOLDERS[k] for k in ("body", "race", "parts", "build")}
