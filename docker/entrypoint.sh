#!/bin/bash
set -e

# Set timezone if provided (only if we have permission)
if [ -n "$TZ" ] && [ -w /etc ]; then
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
fi

# Cache Unraid boot information while running as root (before user switching)
echo "Caching Unraid system information..."

# Try to get hostname from Unraid boot config
if [ -f "/boot/config/ident.cfg" ]; then
    CACHED_HOSTNAME=$(grep "NAME=" /boot/config/ident.cfg 2>/dev/null | cut -d= -f2 | tr -d '"' | head -1)
    if [ -n "$CACHED_HOSTNAME" ]; then
        export CACHED_HOSTNAME
        echo "Cached hostname: $CACHED_HOSTNAME"
    fi
fi

# Try to get Unraid version from changes.txt
if [ -f "/boot/changes.txt" ]; then
    CACHED_UNRAID_VERSION=$(head -1 /boot/changes.txt 2>/dev/null | sed 's/# Version //' | awk '{print $1}')
    if [ -n "$CACHED_UNRAID_VERSION" ]; then
        export CACHED_UNRAID_VERSION
        echo "Cached Unraid version: $CACHED_UNRAID_VERSION"
    fi
fi

# Try alternative version detection in docker.cfg
if [ -z "$CACHED_UNRAID_VERSION" ] && [ -f "/boot/config/docker.cfg" ]; then
    if grep -q "DOCKER_ENABLED" /boot/config/docker.cfg 2>/dev/null; then
        export CACHED_UNRAID_VERSION="Unraid (detected)"
        echo "Cached Unraid version: Unraid (detected from docker.cfg)"
    fi
fi

# Cache template directory accessibility and copy templates
if [ -d "/boot/config/plugins/dockerMan/templates-user" ]; then
    export TEMPLATES_ACCESSIBLE="true"
    echo "Template directory accessible"

    # Create cache directory for templates in /output (persistent location)
    mkdir -p /output/cached-templates

    # Copy all XML templates to cache directory (as root, so we can read them)
    if [ "$(ls -A /boot/config/plugins/dockerMan/templates-user/*.xml 2>/dev/null)" ]; then
        cp /boot/config/plugins/dockerMan/templates-user/*.xml /output/cached-templates/ 2>/dev/null || true
        template_count=$(ls -1 /output/cached-templates/*.xml 2>/dev/null | wc -l)
        echo "Cached $template_count XML templates to /output/cached-templates"
    else
        echo "No XML templates found in templates-user directory"
    fi
else
    export TEMPLATES_ACCESSIBLE="false"
    echo "Template directory not accessible"
fi

# Handle PUID/PGID for Unraid compatibility (only if running as root)
if [ "$(id -u)" = "0" ] && [ -n "$PUID" ] && [ -n "$PGID" ]; then
    echo "Setting up user permissions: PUID=$PUID, PGID=$PGID"

    # Change guardian user/group IDs to match Unraid
    groupmod -o -g "$PGID" guardian 2>/dev/null || true
    usermod -o -u "$PUID" guardian 2>/dev/null || true

    # Update sudo rule for template refresh to work with any UID
    echo "%$PGID ALL=(root) NOPASSWD: /usr/local/bin/refresh-templates.sh" > /etc/sudoers.d/guardian-templates
    chmod 440 /etc/sudoers.d/guardian-templates

    # Ensure proper ownership of key directories
    chown -R guardian:guardian /config /output 2>/dev/null || true

    echo "User setup complete: guardian user now has UID=$(id -u guardian), GID=$(id -g guardian)"
elif [ "$(id -u)" != "0" ]; then
    # Running as non-root user, just ensure directories exist
    echo "Running as non-root user ($(id -u):$(id -g)), ensuring directories exist"
    mkdir -p /config /output 2>/dev/null || true
else
    echo "Running as root but no PUID/PGID specified, using default guardian user (1000:1000)"
fi

# Set up cron job if SCHEDULE is provided
if [ -n "$SCHEDULE" ]; then
    echo "Setting up cron job with schedule: $SCHEDULE"
    PYTHON_BIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
    echo "Using Python interpreter for cron: $PYTHON_BIN"

    # Docker connection settings for cron-triggered backups
    CRON_ENV_VARS=""
    if [ -n "$DOCKER_HOST" ]; then
        CRON_ENV_VARS="$CRON_ENV_VARS DOCKER_HOST=$DOCKER_HOST"
    fi
    if [ -n "$DOCKER_SOCK_PATH" ]; then
        CRON_ENV_VARS="$CRON_ENV_VARS DOCKER_SOCK_PATH=$DOCKER_SOCK_PATH"
    fi
    if [ -n "$DOCKER_TLS_VERIFY" ]; then
        CRON_ENV_VARS="$CRON_ENV_VARS DOCKER_TLS_VERIFY=$DOCKER_TLS_VERIFY"
    fi
    if [ -n "$DOCKER_CERT_PATH" ]; then
        CRON_ENV_VARS="$CRON_ENV_VARS DOCKER_CERT_PATH=$DOCKER_CERT_PATH"
    fi
    CRON_ENV_VARS="${CRON_ENV_VARS#" "}"

    if [ -n "$CRON_ENV_VARS" ]; then
        echo "Cron Docker env: $CRON_ENV_VARS"
    else
        echo "Cron Docker env: none provided (falling back to container defaults)"
    fi

    CRON_CMD="cd /app &&"
    if [ -n "$CRON_ENV_VARS" ]; then
        CRON_CMD="$CRON_CMD $CRON_ENV_VARS"
    fi
    CRON_CMD="$CRON_CMD $PYTHON_BIN src/unraid_config_guardian.py --output /output >> /output/guardian.log 2>&1"

    if [ "$(id -u)" = "0" ]; then
        # Running as root, use crontab for guardian user
        echo "$SCHEDULE $CRON_CMD" | crontab -u guardian - 2>/dev/null || true
        # Start cron in background
        cron & 2>/dev/null || true
    else
        # Running as non-root, use user crontab
        echo "$SCHEDULE $CRON_CMD" | crontab - 2>/dev/null || true
    fi
fi

# Create initial config if it doesn't exist
if [ ! -f /config/config.yml ]; then
    echo "Creating initial configuration..."
    cat > /config/config.yml << EOF
guardian:
  backup:
    mask_passwords: ${MASK_PASSWORDS:-true}
    include_system_info: ${INCLUDE_SYSTEM_INFO:-true}
    output_location: ${BACKUP_LOCATION:-/output}

  notifications:
    webhook_url: ${WEBHOOK_URL:-}
    email: ${EMAIL_NOTIFICATIONS:-}

  debug: ${DEBUG:-false}
EOF

    # Set ownership if running as root
    if [ "$(id -u)" = "0" ]; then
        chown guardian:guardian /config/config.yml 2>/dev/null || true
    fi
fi

# Switch to guardian user and execute command
if [ "$(id -u)" = "0" ] && command -v gosu >/dev/null 2>&1; then
    # Running as root and gosu is available
    if [ "$1" = 'python' ] || [ "$1" = 'src/unraid_config_guardian.py' ] || [ "$1" = 'src/web_gui.py' ]; then
        exec gosu guardian "$@"
    else
        exec "$@"
    fi
else
    # Running as non-root or gosu not available, execute directly
    exec "$@"
fi
