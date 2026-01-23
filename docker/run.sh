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
export PYTHONPATH=$PYTHONPATH:/app

# Run the application
# Check if we're running celery (worker mode) or gunicorn (web mode)
if [[ "$1" == "celery" ]] || [[ "$*" == *"celery"* ]]; then
    echo "Starting Celery Worker..."
    exec sudo -E -u "#${uid}" "$@"
else
    echo "Starting Web Application with Gunicorn..."
    exec sudo -E -u "#${uid}" gunicorn \
        --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
        --workers 1 \
        --bind 0.0.0.0:8465 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        app:app
fi
