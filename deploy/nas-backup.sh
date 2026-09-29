#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
OLD_POSTGRES="semi-vix-platform-postgres-1"
STAMP="$(date +%Y%m%d-%H%M%S)"
CONTAINER_BACKUP="/tmp/semi-vix-before-single-${STAMP}.backup"
HOST_BACKUP="${BACKUP_DIR}/semi-vix-before-single-${STAMP}.backup"

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run this script with sudo.\n' >&2
  exit 1
fi

PROJECT_UID="$(stat -c '%u' "${PROJECT_DIR}")"
PROJECT_GID="$(stat -c '%g' "${PROJECT_DIR}")"
install -d -m 0700 -o "${PROJECT_UID}" -g "${PROJECT_GID}" "${BACKUP_DIR}"
docker inspect "${OLD_POSTGRES}" >/dev/null

was_running="$(docker inspect -f '{{.State.Running}}' "${OLD_POSTGRES}")"
if [[ "${was_running}" != "true" ]]; then
  docker start "${OLD_POSTGRES}" >/dev/null
fi

restore_old_state() {
  if [[ "${was_running}" != "true" ]]; then
    docker stop --time 60 "${OLD_POSTGRES}" >/dev/null 2>&1 || true
  fi
}
trap restore_old_state EXIT

for _ in $(seq 1 60); do
  if docker exec "${OLD_POSTGRES}" pg_isready -U svix -d svix >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${OLD_POSTGRES}" pg_isready -U svix -d svix >/dev/null

docker exec "${OLD_POSTGRES}" pg_dump -U svix -d svix -Fc -f "${CONTAINER_BACKUP}"
docker exec "${OLD_POSTGRES}" pg_restore -l "${CONTAINER_BACKUP}" >/dev/null
docker cp "${OLD_POSTGRES}:${CONTAINER_BACKUP}" "${HOST_BACKUP}"
docker exec "${OLD_POSTGRES}" rm -f "${CONTAINER_BACKUP}"
chown "${PROJECT_UID}:${PROJECT_GID}" "${HOST_BACKUP}"
chmod 0600 "${HOST_BACKUP}"
test -s "${HOST_BACKUP}"

printf 'BACKUP_OK=%s\n' "${HOST_BACKUP}"
sha256sum "${HOST_BACKUP}"
