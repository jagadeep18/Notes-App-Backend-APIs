#!/usr/bin/env bash
# build.sh — Render build script
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Nuke the entire public schema and recreate it — guarantees a clean slate
# Safe because this is a fresh deploy. Remove this block once the initial
# migration has succeeded and you have real data.
python3.11 -c "
import os, asyncio, asyncpg

async def reset():
    url = os.environ.get('DATABASE_URL', '')
    # asyncpg needs postgresql:// not postgresql+asyncpg://
    for prefix in ('postgresql+asyncpg://', 'postgres://'):
        if url.startswith(prefix):
            url = url.replace(prefix, 'postgresql://', 1)
            break
    conn = await asyncpg.connect(url)
    print('Dropping and recreating public schema for clean migration...')
    await conn.execute('DROP SCHEMA public CASCADE')
    await conn.execute('CREATE SCHEMA public')
    await conn.execute('GRANT ALL ON SCHEMA public TO PUBLIC')
    print('Schema reset complete.')
    await conn.close()

asyncio.run(reset())
"

# Run database migrations on the clean schema
python3.11 -m alembic upgrade head
