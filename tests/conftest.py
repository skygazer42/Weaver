import os

pytest_plugins = ["pytest_asyncio"]

# Force in-memory checkpointer during tests to avoid DB dependency
os.environ.setdefault("DATABASE_URL", "")
