FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CONFIG_DIR=/app/config
ENV DATA_DIR=/app/data

# Install system dependencies (including postgresql client for pg_dump)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
    libzstd-dev \
    zlib1g-dev \
    libjpeg-dev \
    libcurl4-openssl-dev \
    sudo \
    curl \
    procps \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir packaging && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
# Copy application code
COPY ./app /app

# Copy scripts directory
COPY ./scripts /app/scripts

# Place docker-ready migrate+backfill helper into /usr/local/bin
COPY ./scripts/docker/migrate_and_backfill.sh /usr/local/bin/migrate_and_backfill.sh
RUN chmod +x /usr/local/bin/migrate_and_backfill.sh

# Copy run script specifically from docker folder
COPY ./docker/run.sh /app/run.sh
COPY ./docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/run.sh /app/entrypoint.sh

# Create necessary directories
RUN mkdir -p /app/config /app/data /games

# Expose port
EXPOSE 8465

# Run the application
ENTRYPOINT [ "/app/entrypoint.sh" ]
