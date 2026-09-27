# Urja Kavach backend (Dev A). One image runs the API + in-process agents.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# curl: container healthcheck. build-essential: fallback in case chromadb's
# hnswlib, scikit-learn, or psycopg have no prebuilt wheel for this platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY backend ./backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Uvicorn serves the ASGI app; startup seeds config + creates tables.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
