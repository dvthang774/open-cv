FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

COPY app /app/app
COPY docker/ai-entrypoint.sh /app/docker/ai-entrypoint.sh

RUN chmod +x /app/docker/ai-entrypoint.sh

CMD ["python", "-m", "app.workers.segment_worker"]

