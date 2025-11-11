FROM python:3.11-slim

# Keep Python output unbuffered
ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5050 \
    GUNICORN_WORKERS=1

# Install system packages required to build some Python wheels (PyAudio/portaudio)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        libssl-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only server requirements first to leverage Docker layer caching
COPY requirements.txt /app/

# Upgrade pip and install Python dependencies required for the server
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    # Remove build-time packages to reduce final image size
    && apt-get purge -y build-essential gcc libffi-dev libssl-dev python3-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY . /app

# Expose the port the Flask app listens on (default 5050 in server.py)
EXPOSE 5050

# Run the server with Gunicorn using the eventlet worker (works with Flask-SocketIO)
# Bind address/port come from the server config (default 0.0.0.0:5050)
CMD gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" -w ${GUNICORN_WORKERS} -b 0.0.0.0:${FLASK_PORT} patched:app
