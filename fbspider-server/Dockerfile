# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12.10-slim-bookworm
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
# Overwrite frontend dir with only the build output (no node_modules)
RUN rm -rf frontend
COPY --from=frontend-build /frontend/dist frontend/dist

EXPOSE 7150 7671

CMD ["gunicorn", "--bind", "0.0.0.0:7150", "--worker-class", "gthread", "--threads", "8", "--workers", "1", "--keep-alive", "0", "--timeout", "120", "app:app"]
