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

# System packages: tini (proper PID 1), curl (debugging).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer).
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app/backend

# Backend source (after deps so code edits don't bust the deps cache).
COPY backend/ ./backend/

# Built frontend static files.
COPY --from=frontend /build/dist ./frontend/dist

# Add-on entrypoint.
COPY run.sh /run.sh
RUN chmod +x /run.sh

# /data is mounted by HA Add-on supervisor; persists DB + config.json across restarts.
ENV DB_PATH=/data/climate.db \
    CONFIG_PATH=/data/config.json \
    CONFIG_DEFAULT_PATH=/app/backend/data/config.default.json \
    FRONTEND_DIST=/app/frontend/dist \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/run.sh"]
