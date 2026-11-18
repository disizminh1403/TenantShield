"""TenantShield Plus: add-on features that reuse the main `tenantshield` package."""

from pathlib import Path
import sys

PLUS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUS_DIR.parent

# The add-on lives in its own folder but shares search, validation and map code with the main app.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
