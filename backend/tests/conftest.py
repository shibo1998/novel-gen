"""pytest configuration for tests directory"""
import sys
from pathlib import Path

import pytest

# Ensure backend root is on path so 'app' can be imported
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


@pytest.fixture(scope="session", autouse=True)
async def close_database_pool_after_tests():
    """Release asyncpg connections before pytest closes its event loop."""
    yield
    from app.db.session import close_db

    await close_db()
