#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_ID="${1:-v1.0}"
if [[ ! "${RELEASE_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  printf 'Invalid release ID: %s\n' "${RELEASE_ID}" >&2
  exit 1
fi

# This overlay may replace the entrypoint script, but requires unchanged
# runtime packages, binaries, and dependencies from image b5eddf1.
runtime_changes="$(git -C "${ROOT}" diff --name-only b5eddf1 -- \
  Dockerfile docker go go.mod go.sum requirements.txt requirements-futu.txt \
  frontend/pnpm-lock.yaml frontend/package-lock.json | rg -v '^docker/entrypoint\.sh$' || true)"
if [[ -n "${runtime_changes}" ]]; then
  printf 'Runtime or dependency files changed; build a full amd64 image instead.\n' >&2
  exit 1
fi
if ! node - "${ROOT}" <<'NODE'
const fs = require('node:fs')
const { execFileSync } = require('node:child_process')
const root = process.argv[2]
const current = JSON.parse(fs.readFileSync(`${root}/frontend/package.json`, 'utf8'))
const baseline = JSON.parse(execFileSync('git', ['-C', root, 'show', 'b5eddf1:frontend/package.json'], { encoding: 'utf8' }))
for (const field of ['dependencies', 'devDependencies']) {
  if (JSON.stringify(current[field]) !== JSON.stringify(baseline[field])) process.exit(1)
}
NODE
then
  printf 'Frontend dependencies changed; build a full amd64 image instead.\n' >&2
  exit 1
fi

cd "${ROOT}/frontend"
npm run build

OUT_DIR="${ROOT}/releases/nas-code-${RELEASE_ID}"
mkdir -p "${OUT_DIR}"
ARCHIVE="${OUT_DIR}/semi-vix-code-${RELEASE_ID}.tar.gz"
tar -czf "${ARCHIVE}" --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' -C "${ROOT}" \
  backend/app backend/alembic backend/alembic.ini frontend/dist docker/entrypoint.sh
(cd "${OUT_DIR}" && shasum -a 256 "$(basename "${ARCHIVE}")" > SHA256SUMS)
printf 'CODE_OVERLAY=%s\n' "${ARCHIVE}"
printf 'SHA256SUMS=%s\n' "${OUT_DIR}/SHA256SUMS"
