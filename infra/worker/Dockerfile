# Worker Dockerfile — Celery workers (io, cpu, gpu queues)
# Extends the base backend image with optional GPU/ML dependencies.
# The gpu profile adds CUDA-capable libs; the cpu worker uses this same image.
#
# AGENTS.md §3 specifies a dedicated worker/Dockerfile distinct from
# infra/backend/Dockerfile (which serves the Django API).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    # Required by opencv-python-headless (libGL, libSM, etc.)
    libsm6 \
    libxext6 \
    libxrender-dev \
    # Required by yt-dlp for merging formats
    python3-mutagen \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Optional: heavy ML deps that are only needed in the worker, not the API.
# Uncomment to install when running a GPU-enabled worker:
# RUN pip install whisperx torch torchaudio --index-url https://download.pytorch.org/whl/cu121

COPY backend /app
COPY schemas /app/schemas

# Default: cpu+io worker — override CMD in docker-compose for gpu queue.
CMD ["celery", "-A", "config", "worker", "--loglevel=info", "--concurrency=2", "-Q", "io,cpu"]
