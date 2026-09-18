#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:=svix}"
: "${POSTGRES_USER:=svix}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD

if [[ ! "${POSTGRES_DB}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]]; then
  printf 'Invalid POSTGRES_DB: use letters, numbers, underscore, dot or dash.\n' >&2
  exit 1
fi
if [[ ! "${POSTGRES_USER}" =~ ^[A-Za-z_][A-Za-z0-9_.-]*$ ]]; then
  printf 'Invalid POSTGRES_USER: use letters, numbers, underscore, dot or dash.\n' >&2
  exit 1
fi

# This image always uses its embedded PostgreSQL. Rebuild the URL
# here so an existing multi-container .env continues to work without edits.
database_password_encoded="$(python -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"], safe=""))')"
export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${database_password_encoded}@127.0.0.1:5432/${POSTGRES_DB}"

install -d -m 0700 -o postgres -g postgres "${PGDATA}"
install -d -m 0775 -o postgres -g postgres /var/run/postgresql
install -d -m 0775 -o svix -g svix /run/svix
rm -f /run/svix/migrations-complete

# postgres:16-alpine and postgres:16-bookworm use different numeric users.
# Correct ownership once; the marker avoids a recursive scan on every restart.
ownership_marker="${PGDATA}/.svix-owner-$(id -u postgres)"
if [[ ! -e "${ownership_marker}" ]]; then
  chown -R postgres:postgres "${PGDATA}"
  gosu postgres touch "${ownership_marker}"
fi

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  password_file="$(mktemp)"
  trap 'rm -f "${password_file}"' EXIT
  printf '%s' "${POSTGRES_PASSWORD}" >"${password_file}"
  chown postgres:postgres "${password_file}"
  chmod 0600 "${password_file}"
  gosu postgres /usr/lib/postgresql/16/bin/initdb \
    --username="${POSTGRES_USER}" \
    --pwfile="${password_file}" \
    --auth-local=trust \
    --auth-host=scram-sha-256
  rm -f "${password_file}"
  trap - EXIT
fi

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
