"""
tests/unit/conftest.py
──────────────────────
Unit test conftest — NO database setup.
Unit tests test pure functions; they don't touch the DB.
The root conftest.py's `create_test_tables` autouse fixture is excluded here
via a separate conftest override.
"""
from __future__ import annotations

import os

# Set env vars BEFORE any app imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./unit_test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_min_32_chars_long!!")
os.environ.setdefault("ENCRYPTION_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")
