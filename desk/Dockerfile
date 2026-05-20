# syntax=docker/dockerfile:1.6

# Stage 1: build the frontend
FROM node:20-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: backend runtime
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml ./backend/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/backend

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENV DB_PATH=/data/desk.db \
    FRONTEND_DIST=/app/frontend/dist \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/run.sh"]
