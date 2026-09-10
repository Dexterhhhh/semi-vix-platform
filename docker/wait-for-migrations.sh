#!/usr/bin/env bash
set -Eeuo pipefail

for _ in $(seq 1 120); do
  [[ -f /run/svix/migrations-complete ]] && exec "$@"
  sleep 1
done

printf 'Timed out waiting for database migrations.\n' >&2
exit 1

