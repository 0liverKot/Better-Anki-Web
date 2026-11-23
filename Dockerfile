# Build the frontend
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Backend + built frontend. python:3.12-slim (Debian bookworm, glibc 2.36) meets the
# anki wheel's manylinux_2_35 requirement.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BAW_DATA_DIR=/data \
    BAW_FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 1000 baw && mkdir -p /data && chown baw:baw /data
USER baw
VOLUME /data
EXPOSE 8000
# Exactly one worker: an Anki collection must only be opened by one process.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
