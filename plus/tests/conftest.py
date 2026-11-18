"""Make the add-on package importable when pytest runs from the repository root."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
