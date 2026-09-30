#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -f go.mod ] && [ -f ../go.mod ]; then cd ..; fi
if [ -f .env ]; then
  printf '%s\n' '.env already exists; keep it for database and credential compatibility.'
  exit 1
fi
command -v openssl >/dev/null 2>&1 || { printf '%s\n' 'openssl is required.' >&2; exit 1; }
umask 077
config_file=$(mktemp .env.XXXXXX)
trap 'rm -f "$config_file"' EXIT HUP INT TERM
{
  printf 'SECRET_KEY=%s\n' "$(openssl rand -hex 32)"
  printf 'SECRET_ENCRYPTION_KEY=%s\n' "$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  printf 'CREDENTIAL_MASTER_KEY=%s\n' "$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  printf 'POSTGRES_DB=svix\nPOSTGRES_USER=svix\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  printf 'SVIX_ADMIN_USERNAME=admin\nSVIX_ADMIN_PASSWORD=%s\n' "$(openssl rand -hex 16)"
  printf 'DATA_PROVIDER=ALPACA\nCOOKIE_SECURE=false\nSVIX_BIND_ADDRESS=127.0.0.1\nSVIX_HTTP_PORT=\n'
  printf 'IBKR_HOST=host.docker.internal\nFUTU_HOST=host.docker.internal\n'
} > "$config_file"
# Hard-link creation refuses to replace an existing config, including concurrent runs.
ln "$config_file" .env
printf '%s\n' 'Created .env (mode 600). Read your local administrator password there; keep it private.'
