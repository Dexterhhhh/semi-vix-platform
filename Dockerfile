FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "${NPM_REGISTRY}"
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS python-build

ENV PIP_NO_CACHE_DIR=1
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt /tmp/requirements.txt
COPY requirements-futu.txt /tmp/requirements-futu.txt
RUN pip install --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt
ARG INSTALL_FUTU=false
RUN if [ "${INSTALL_FUTU}" = "true" ]; then \
      pip install --index-url "${PIP_INDEX_URL}" -r /tmp/requirements-futu.txt; \
    fi


# Keep PostgreSQL 16 as the final base so an existing Compose postgres_data
# volume can be mounted directly without a database major-version conversion.
FROM postgres:16-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/svix \
    PGDATA=/var/lib/postgresql/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx redis-server supervisor curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && useradd --system --create-home --home-dir /home/svix --shell /usr/sbin/nologin svix \
    && install -d -o svix -g svix /opt/svix/backend /run/svix \
    && install -d -o redis -g redis /var/lib/redis

COPY --from=python-build /usr/local /usr/local
COPY --from=frontend-build /build/frontend/dist /usr/share/nginx/html
COPY --chown=svix:svix backend/ /opt/svix/backend/
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/entrypoint.sh docker/start-backend.sh docker/wait-for-migrations.sh /usr/local/bin/
COPY docker/ensure_database.py /opt/svix/ensure_database.py

RUN chmod 0755 /usr/local/bin/entrypoint.sh /usr/local/bin/start-backend.sh /usr/local/bin/wait-for-migrations.sh

WORKDIR /opt/svix/backend
EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD curl --fail --silent http://127.0.0.1/health >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

