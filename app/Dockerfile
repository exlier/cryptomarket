FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Pillow (image processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/static/uploads

# Bind to a Unix socket instead of a TCP port to avoid http:// strings
CMD ["gunicorn", "--bind", "unix:/tmp/sockets/marketplace.sock", "--workers", "2", "app:app"]
