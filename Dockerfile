# Use Python slim image optimized for long-running stability
FROM python:3.9-slim

# Set working directory
WORKDIR /usr/src/app

# Install minimal system dependencies (Amazon-only support - no Chrome needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    procps \
    psmisc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Note: Chrome and ChromeDriver removed since Amazon tracker uses requests/BeautifulSoup only

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for persistent storage
RUN mkdir -p /data

# Set environment variables (Amazon tracking - no Chrome needed)
ENV DATA_DIR=/data

# Note: Chrome-related environment variables removed since Amazon tracker uses requests only

# Python optimization for Docker
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Memory management
ENV MALLOC_ARENA_MAX=2

# Create a volume for persistent data storage
VOLUME ["/data"]

# Health check to monitor application health
HEALTHCHECK --interval=30m --timeout=30s --start-period=5m --retries=3 \
  CMD pgrep -f "python.*main.py" > /dev/null || exit 1

# Command to run the application
CMD ["python", "main.py"]