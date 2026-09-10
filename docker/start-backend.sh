#!/usr/bin/env bash
set -Eeuo pipefail

for _ in $(seq 1 60); do
  if pg_isready -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d postgres >/dev/null 2>&1 \
    && redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q '^PONG$'; then
    break
  fi
  sleep 1
done

pg_isready -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d postgres >/dev/null
redis-cli -h 127.0.0.1 ping | grep -q '^PONG$'

python /opt/svix/ensure_database.py
cd /opt/svix/backend
alembic upgrade head
touch /run/svix/migrations-complete

exec uvicorn app.main:app --host 127.0.0.1 --port 8000

