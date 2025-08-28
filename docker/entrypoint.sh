#!/bin/bash
set -e

# Set timezone if provided (only if we have permission)
if [ -n "$TZ" ] && [ -w /etc ]; then
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
fi

# Handle PUID/PGID for Unraid compatibility (only if running as root)
if [ "$(id -u)" = "0" ] && [ -n "$PUID" ] && [ -n "$PGID" ]; then
    # Change guardian user/group IDs to match Unraid
    groupmod -o -g "$PGID" guardian 2>/dev/null || true
    usermod -o -u "$PUID" guardian 2>/dev/null || true

    # Ensure proper ownership
    chown -R guardian:guardian /config /output /app 2>/dev/null || true
elif [ "$(id -u)" != "0" ]; then
    # Running as non-root user, just ensure directories exist
    mkdir -p /config /output 2>/dev/null || true
fi

# Set up cron job if SCHEDULE is provided
if [ -n "$SCHEDULE" ]; then
    echo "Setting up cron job with schedule: $SCHEDULE"
    if [ "$(id -u)" = "0" ]; then
        # Running as root, use crontab for guardian user
        echo "$SCHEDULE cd /app && python src/unraid_config_guardian.py --output /output >> /output/guardian.log 2>&1" | crontab -u guardian - 2>/dev/null || true
        # Start cron in background
        cron & 2>/dev/null || true
    else
        # Running as non-root, use user crontab
        echo "$SCHEDULE cd /app && python src/unraid_config_guardian.py --output /output >> /output/guardian.log 2>&1" | crontab - 2>/dev/null || true
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
