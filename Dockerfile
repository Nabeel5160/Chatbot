FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ChatbotDocument.txt ./ChatbotDocument.txt

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Render/Fly set PORT; default 8000 for local Docker
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
