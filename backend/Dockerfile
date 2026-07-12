FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt
ARG INSTALL_FUTU=false
COPY requirements-futu.txt ./
RUN if [ "$INSTALL_FUTU" = "true" ]; then pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements-futu.txt; fi
RUN addgroup --system svix && adduser --system --ingroup svix svix
COPY --chown=svix:svix backend /app/backend
WORKDIR /app/backend
EXPOSE 8000
USER svix
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
