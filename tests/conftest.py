"""
tests/conftest.py
──────────────────
Root conftest — only env var setup. No DB autouse.
DB setup lives in tests/integration/conftest.py.
"""
from __future__ import annotations

import os

# Must be set before ANY app module is imported
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_min_32_chars_long!!")
os.environ.setdefault("ENCRYPTION_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")
