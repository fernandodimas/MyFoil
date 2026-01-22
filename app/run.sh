#!/bin/bash

# Retrieve from Environment variables, or use 1000 as default
gid=${PGID:-1000}
uid=${PUID:-1000}

# Create group if it doesn't exist
if ! getent group "${gid}" >/dev/null; then
    groupadd -g "${gid}" myfoil
fi

# Create user if it doesn't exist
if ! getent passwd "${uid}" >/dev/null; then
    useradd -u "${uid}" -g "${gid}" -m -s /bin/bash myfoil
fi

# Set permissions
chown -R ${uid}:${gid} /app
chown -R ${uid}:${gid} /games 2>/dev/null || true

echo "Starting MyFoil as UID ${uid}..."

# Run the application
if [ "$1" = "worker" ]; then
    echo "Starting Celery Worker..."
    exec sudo -E -u "#${uid}" celery -A app.celery_app.celery worker --loglevel=info
else
    echo "Starting Web Application..."
    exec sudo -E -u "#${uid}" python /app/app.py
fi
