FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "${NPM_REGISTRY}"
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test && npm run build

FROM golang:1.26.4-alpine3.24 AS go-build
WORKDIR /build
ARG GOPROXY=https://proxy.golang.org,direct
COPY go.mod go.sum ./
COPY go/ ./go/
ARG EDITION=full
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go test ./go/... \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X github.com/Dexterhhhh/semi-vix-platform/go/internal/providers.BuildEdition=${EDITION}" -o /out/svix-engine ./go/cmd/svix-engine \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X github.com/Dexterhhhh/semi-vix-platform/go/internal/providers.BuildEdition=${EDITION}" -o /out/svix-scheduler ./go/cmd/svix-scheduler \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X github.com/Dexterhhhh/semi-vix-platform/go/internal/providers.BuildEdition=${EDITION}" -o /out/svix-runtime ./go/cmd/svix-runtime

FROM python:3.12-slim-bookworm AS python-build
ENV PIP_NO_CACHE_DIR=1
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements-runtime.txt requirements-futu.txt /tmp/
RUN pip install --index-url "${PIP_INDEX_URL}" -r /tmp/requirements-runtime.txt -r /tmp/requirements-futu.txt
COPY backend/app/ /src/backend/app/
COPY docker/sdk-files.txt /tmp/sdk-files.txt
RUN while IFS= read -r file; do \
        mkdir -p "/sdk/$(dirname "$file")" \
        && cp "/src/$file" "/sdk/$file" || exit 1; \
    done < /tmp/sdk-files.txt

# No architecture is pinned: Docker selects the requested build platform.
FROM postgres:16-bookworm
ENV HOME=/home/svix PGDATA=/var/lib/postgresql/data DATA_PROVIDER=ALPACA
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && useradd --system --create-home --home-dir /home/svix --shell /usr/sbin/nologin svix \
    && install -d -o svix -g svix /opt/svix/backend /run/svix
COPY --from=go-build /out/ /usr/local/bin/
COPY --from=frontend-build /build/frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh
COPY --from=python-build /usr/local /usr/local
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=python-build --chown=svix:svix /sdk/backend/app/ /opt/svix/backend/app/
WORKDIR /opt/svix/backend
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=8s --start-period=90s --retries=5 \
    CMD ["/usr/local/bin/svix-runtime", "--healthcheck"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
