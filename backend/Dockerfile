FROM python:3.11-slim

# Keras 3 runs the supplied MLP on its inference-only numpy backend, so the
# image needs no TensorFlow. Set here so it applies to every process.
ENV KERAS_BACKEND=numpy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# curl is only needed for the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements first so the (slow) dependency layer is cached across code edits.
COPY requirements.txt requirements-dev.txt ./
# Test deps are included so the suite can be run inside the container with
#   docker compose exec backend pytest
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app/ ./app/
COPY models/ ./models/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY pytest.ini ./

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
