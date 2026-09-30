#!/usr/bin/env bash
# Starts and removes its own database; never mounts the application's data volume.
set -Eeuo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"
test_container="svix-go-integration-$$"
trap 'docker rm -f "$test_container" >/dev/null 2>&1 || true' EXIT
python_bin="${SVIX_TEST_PYTHON:-$root_dir/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo 'Set SVIX_TEST_PYTHON to a Python environment with requirements-dev.txt installed.' >&2
  exit 1
fi
docker run --rm -d --name "$test_container" -p 127.0.0.1::5432 \
  -e POSTGRES_PASSWORD=integration-only -e POSTGRES_DB=svix_go_test postgres:16-bookworm >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$test_container" pg_isready -h 127.0.0.1 -U postgres -d svix_go_test >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$test_container" pg_isready -h 127.0.0.1 -U postgres -d svix_go_test >/dev/null
test_port="$(docker port "$test_container" 5432/tcp | sed 's/.*://')"
export DATABASE_URL="postgresql+psycopg://postgres:integration-only@127.0.0.1:$test_port/svix_go_test"
export SVIX_TEST_DATABASE_URL="$DATABASE_URL"
export SECRET_KEY=integration-only SECRET_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
export CREDENTIAL_MASTER_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
export SVIX_ADMIN_USERNAME=go-test-admin SVIX_ADMIN_PASSWORD=local-test-only
export SVIX_TEST_ADMIN_PASSWORD=local-test-only
(cd backend && "$python_bin" -m alembic upgrade head)
# The suites intentionally share disposable fixtures and run sequentially.
go test -count=1 -v ./go/internal/database
go test -count=1 -v ./go/internal/service
go test -count=1 -v ./go/internal/api
go test -count=1 -v ./go/internal/auth
