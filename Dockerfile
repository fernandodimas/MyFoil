FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CONFIG_DIR=/app/config
ENV DATA_DIR=/app/data

# Install system dependencies
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

# Copy run script specifically from docker folder
COPY ./docker/run.sh /app/run.sh
RUN chmod +x /app/run.sh

# Create necessary directories
RUN mkdir -p /app/config /app/data /games

# Expose port
EXPOSE 8465

# Run the application
ENTRYPOINT [ "/app/run.sh" ]
