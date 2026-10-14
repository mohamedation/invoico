FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY samples ./samples
COPY eval ./eval
COPY fx ./fx
COPY .streamlit ./.streamlit
COPY .env.example ./.env.example

RUN mkdir -p /app/data/uploads \
    && python scripts/make_samples.py || true

ENV PYTHONUNBUFFERED=1
ENV OLLAMA_HOST=http://host.docker.internal:11434
ENV MODEL=gemma4:e2b
ENV API_BASE=http://api:8000

EXPOSE 8000 8501
