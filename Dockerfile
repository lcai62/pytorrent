# ----------  build backend  ----------
FROM python:3.11-slim AS backend
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENV PYTHONPATH=/app

# ----------  build frontend  ----------
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend ./
RUN npm run build    # outputs to /frontend/build

# ----------  final image  ----------
FROM python:3.11-slim
WORKDIR /app
# copy backend site-packages
COPY --from=backend /usr/local/lib/python*/site-packages /usr/local/lib/python*/site-packages
COPY --from=backend /app/src ./src
# copy static React build
COPY --from=frontend /frontend/build ./static
EXPOSE 8000
CMD ["uvicorn", "src.fastapi_server:app", "--host", "0.0.0.0", "--port", "8000"]
