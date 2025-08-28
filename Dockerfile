FROM python:3.11-slim

LABEL maintainer="Stephon Parker <sgparker62@gmail.com>"
LABEL description="Unraid Config Guardian - Disaster recovery documentation for Unraid servers"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd -g 1000 guardian && \
    useradd -u 1000 -g guardian -s /bin/bash -m guardian

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    cron \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY templates/ ./templates/

# Create directories for configuration and output
RUN mkdir -p /config /output && \
    chown -R guardian:guardian /app /config /output

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# For development, we might need to run as current user
# USER guardian

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python src/health_check.py || exit 1

# Expose port for web interface (if implemented)
EXPOSE 8080

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "src/web_gui.py"]