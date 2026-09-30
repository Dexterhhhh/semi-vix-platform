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

# The Go runtime builds the database URL and applies schema migrations.

install -d -m 0700 -o postgres -g postgres "${PGDATA}"
install -d -m 0775 -o postgres -g postgres /var/run/postgresql
install -d -m 0775 -o svix -g svix /run/svix
rm -f /run/svix/migrations-complete

# postgres:16-alpine and postgres:16-bookworm use different numeric users.
# Correct ownership once; the marker avoids a recursive scan on every restart.
ownership_marker="${PGDATA}/.svix-owner-$(id -u postgres)"
if [[ ! -e "${ownership_marker}" ]]; then
  chown -R postgres:postgres "${PGDATA}"
fi

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  # A marker in an uninitialized volume makes initdb reject the directory.
  rm -f "${ownership_marker}"
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
gosu postgres touch "${ownership_marker}"

exec /usr/local/bin/svix-runtime
