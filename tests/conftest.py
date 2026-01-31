import os
import sys
from pathlib import Path

import pytest

pytest_plugins = ["pytest_asyncio"]

# Force in-memory checkpointer during tests to avoid DB dependency
os.environ.setdefault("DATABASE_URL", "")

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_collect_file(file_path: Path, parent):
    # Workaround Windows special device "nul" that PyTest trips on
    if file_path.name.lower() == "nul":
        return None
