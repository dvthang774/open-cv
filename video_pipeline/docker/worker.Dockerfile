FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir -U pip

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

COPY app /app/app

CMD ["python", "-m", "app.workers.segment_worker"]

