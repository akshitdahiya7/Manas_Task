FROM python:3.11-slim

# Keras runs the MLP on its numpy backend, so no TensorFlow is needed.
ENV KERAS_BACKEND=numpy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# curl is for the healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements first so the slow dependency layer stays cached.
COPY requirements.txt requirements-dev.txt ./
# Includes test deps so `docker compose exec backend pytest` works.
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app/ ./app/
COPY models/ ./models/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY pytest.ini ./

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
