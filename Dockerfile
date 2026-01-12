# Build stage
FROM python:3.11-slim-bookworm AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    python3-dev \
    libzstd-dev \
    zlib1g-dev \
    libjpeg-dev \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage
FROM python:3.11-slim-bookworm

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Metadata
LABEL maintainer="Myfoil Team"
LABEL description="Enhanced Nintendo Switch library manager and Tinfoil Shop"

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY ./app /app
COPY ./docker/run.sh /app/run.sh
RUN chmod +x /app/run.sh

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV CONFIG_DIR=/app/config
ENV DATA_DIR=/app/data

# Create necessary directories
RUN mkdir -p /app/config /app/data /games

# Expose port
EXPOSE 8465

# Run the application
ENTRYPOINT [ "/app/run.sh" ]
