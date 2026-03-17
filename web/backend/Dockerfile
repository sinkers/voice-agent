# Stage 1: build the React frontend
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY ../frontend/package*.json ./
RUN npm ci
COPY ../frontend/ ./
# VITE_API_URL is empty string so fetch calls go to the same origin
RUN VITE_API_URL="" npm run build

# Stage 2: Python backend + static files
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" livekit-api python-dotenv

COPY main.py .

# Copy built frontend
COPY --from=frontend /frontend/dist ./static

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
