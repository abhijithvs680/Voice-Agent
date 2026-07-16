# Voice Agent — container image
# Pipecat's audio/ML deps need Python 3.11/3.12; we use 3.12-slim.
FROM python:3.12-slim

# System deps: build tools for native wheels, and ffmpeg/libsndfile for audio.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8888

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and knowledge base.
COPY app/ app/
COPY knowledge/ knowledge/

EXPOSE 8888

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8888"]
