FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir -U pip

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

COPY app /app/app
COPY main.py /app/main.py

EXPOSE 8000
CMD ["uvicorn", "app.interface.api:app", "--host", "0.0.0.0", "--port", "8000"]

