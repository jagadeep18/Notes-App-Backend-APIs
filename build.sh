#!/usr/bin/env bash
# build.sh — Render build script
# Render runs this during every deploy

set -o errexit  # exit on error

pip install --upgrade pip
pip install -r requirements.txt

# Clean up any partially-applied migration state and re-run
# This handles cases where a previous deploy failed mid-migration
python -c "
import os, asyncio, asyncpg

async def clean():
    url = os.environ.get('DATABASE_URL', '')
    if url.startswith('postgresql+asyncpg://'):
        url = url.replace('postgresql+asyncpg://', 'postgresql://', 1)
    conn = await asyncpg.connect(url)
    # Drop all tables/types if alembic_version doesn't exist (partial migration)
    has_alembic = await conn.fetchval(
        \"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version')\"
    )
    if not has_alembic:
        print('No alembic_version table — cleaning up partial migration artifacts...')
        for table in ['activity_logs','share_links','note_versions','note_shares','notes','users']:
            await conn.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
        await conn.execute('DROP TYPE IF EXISTS note_permission_enum')
        await conn.execute('DROP TYPE IF EXISTS action_type_enum')
        await conn.execute('DROP FUNCTION IF EXISTS notes_search_vector_update() CASCADE')
        await conn.execute('DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE')
        print('Cleanup done.')
    else:
        print('alembic_version exists — running normal migration.')
    await conn.close()

asyncio.run(clean())
"

# Run database migrations
alembic upgrade head
