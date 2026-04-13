FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package + its runtime deps. Copying sources before install
# because setuptools.find needs them; not optimizing for layer caching here
# since the project is small.
COPY pyproject.toml alembic.ini ./
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

RUN pip install .

# Photo upload volume. Persisted at runtime via a docker volume mount.
RUN mkdir -p /data/photos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request, sys; \
    sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
