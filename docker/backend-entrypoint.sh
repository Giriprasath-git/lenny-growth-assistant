#!/bin/bash
set -e

echo "=============================================================================="
echo " Starting The Lenny Growth Assistant - Backend Container"
echo "=============================================================================="

# 1. Wait for PostgreSQL to become reachable and ready
echo "[Entrypoint 1/3] Waiting for PostgreSQL database connection..."
python - << 'EOF'
import asyncio
import os
import sys
from urllib.parse import urlparse

async def wait_for_db():
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/lenny_growth_db")
    clean_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(clean_url)
    host = parsed.hostname or "db"
    port = parsed.port or 5432
    user = parsed.username or "postgres"
    password = parsed.password or "postgres"
    database = parsed.path.lstrip("/") or "lenny_growth_db"

    import asyncpg
    max_retries = 30
    for attempt in range(1, max_retries + 1):
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=5.0
            )
            await conn.close()
            print(f"[Entrypoint] Successfully connected to PostgreSQL at {host}:{port}/{database}")
            return
        except Exception as e:
            if attempt % 5 == 0:
                print(f"[Entrypoint] Still waiting for PostgreSQL ({attempt}/{max_retries})...")
            await asyncio.sleep(1)

    print("[Entrypoint] ERROR: Timed out waiting for PostgreSQL.", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait_for_db())
EOF

# 2. Run Alembic database migrations idempotently
echo "[Entrypoint 2/3] Applying Alembic database migrations..."
cd /app/backend
alembic upgrade head
cd /app

# 3. Launch FastAPI ASGI server with Uvicorn
echo "[Entrypoint 3/3] Starting FastAPI Uvicorn server on port 8000..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
