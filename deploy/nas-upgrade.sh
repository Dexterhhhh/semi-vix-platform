#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/volume1/homes/dexterma/docker/semi-vix-platform"
ARCHIVE="/volume1/homes/dexterma/docker/semi-vix-single-upgrade.tar.gz"
BACKUP_DIR="${PROJECT_DIR}/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
SOURCE_BACKUP="${BACKUP_DIR}/source-before-single-${STAMP}.tar.gz"

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run this script with sudo.\n' >&2
  exit 1
fi
if [[ ! -s "${ARCHIVE}" ]]; then
  printf 'Upgrade archive is missing: %s\n' "${ARCHIVE}" >&2
  exit 1
fi
if ! find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'semi-vix-before-single-*.backup' -size +0c | grep -q .; then
  printf 'A verified pre-upgrade database backup is required.\n' >&2
  exit 1
fi

tar -czf "${SOURCE_BACKUP}" \
  --exclude='./backups' \
  --exclude='./.git' \
  -C "${PROJECT_DIR}" .
chown dexterma:users "${SOURCE_BACKUP}"
chmod 0600 "${SOURCE_BACKUP}"

tar -xzf "${ARCHIVE}" -C "${PROJECT_DIR}"
chown -R dexterma:users "${PROJECT_DIR}"
chmod 0600 "${PROJECT_DIR}/.env"

cd "${PROJECT_DIR}"
docker compose config --quiet

# Build before removing any old container. A download or compile failure leaves
# the old deployment intact and the PostgreSQL volume untouched.
docker compose build app

# Never add -v here: the existing PostgreSQL 16 named volume is the migration path.
docker compose down --remove-orphans
docker compose up -d --no-build --remove-orphans

for _ in $(seq 1 90); do
  if docker compose exec -T app curl --fail --silent http://127.0.0.1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T app curl --fail --silent http://127.0.0.1/health
printf '\n'

container_count="$(docker compose ps -q | wc -l | tr -d ' ')"
if [[ "${container_count}" != "1" ]]; then
  printf 'Expected one Compose container, found %s.\n' "${container_count}" >&2
  docker compose ps
  exit 1
fi

docker compose exec -T app supervisorctl status
docker compose exec -T app bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -l'
docker compose ps
printf 'UPGRADE_OK source_backup=%s\n' "${SOURCE_BACKUP}"

