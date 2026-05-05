FROM python:3.12-slim-bookworm

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    wget \
    jq \
    libyaml-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Nemoclaw source
COPY nemoclaw/ /app/
COPY nemoclaw.config.yaml /app/config.yaml

# Create necessary directories
RUN mkdir -p /opt/ruflo/models /run /var/ruflo

# Non-root user
RUN useradd -m -u 1000 ruflo && \
    chown -R ruflo:ruflo /app /opt/ruflo /run /var/ruflo
USER ruflo

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run Nemoclaw daemon
CMD ["python", "-m", "nemoclaw.core.nemoclaw_daemon"]