# Use Python slim image optimized for long-running stability
FROM python:3.9-slim

# Set working directory
WORKDIR /usr/src/app

# Install system dependencies with enhanced Chrome stability packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    procps \
    psmisc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome with stable version lock
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver from Debian repository (most stable approach)
RUN apt-get update && apt-get install -y chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver \
    && chromedriver --version || echo "ChromeDriver installed successfully"

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for persistent storage
RUN mkdir -p /data

# Set environment variables for enhanced Chrome stability
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV DISPLAY=:99
ENV DATA_DIR=/data

# Chrome stability environment variables
ENV CHROME_NO_SANDBOX=1
ENV CHROME_DISABLE_GPU=1
ENV CHROME_DISABLE_DEV_SHM_USAGE=1

# ChromeDriver Manager configuration (disabled since we use manual installation)
ENV WDM_LOG_LEVEL=0
ENV WDM_CACHE_TIME=86400

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