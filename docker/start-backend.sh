#!/usr/bin/env bash
set -Eeuo pipefail

for _ in $(seq 1 60); do
  if pg_isready -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d postgres >/dev/null 2>&1 \
    && curl --fail --silent http://127.0.0.1:8090/health >/dev/null; then
    break
  fi
  sleep 1
done

pg_isready -h 127.0.0.1 -p 5432 -U "${POSTGRES_USER}" -d postgres >/dev/null
curl --fail --silent http://127.0.0.1:8090/health >/dev/null

python /opt/svix/ensure_database.py
cd /opt/svix/backend
alembic upgrade head
touch /run/svix/migrations-complete

exec uvicorn app.main:app --host 127.0.0.1 --port 8000
