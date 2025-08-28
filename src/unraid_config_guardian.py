#!/usr/bin/env python3
"""
Unraid Config Guardian
Simple script to document your Unraid setup for disaster recovery

Author: Stephon Parker (stephondoestech)
"""

import argparse
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

import yaml

import docker

# Removed unused imports: Any, Dict, List


def get_containers():
    """Get all Docker containers and their info."""
    client = docker.from_env()
    containers = []

    for container in client.containers.list(all=True):
        # Extract basic info
        info = {
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else "unknown",
            "status": container.status,
            "ports": [],
            "volumes": [],
            "environment": {},
        }

        # Get ports
        ports = container.attrs["NetworkSettings"]["Ports"] or {}
        for container_port, host_bindings in ports.items():
            if host_bindings:
                host_port = host_bindings[0]["HostPort"]
                info["ports"].append(f"{host_port}:{container_port}")

        # Get volumes
        for mount in container.attrs["Mounts"] or []:
            if mount["Type"] == "bind":
                info["volumes"].append(f"{mount['Source']}:{mount['Destination']}")

        # Get environment (mask sensitive data)
        for env_var in container.attrs["Config"]["Env"] or []:
            if "=" in env_var:
                key, value = env_var.split("=", 1)
                # Simple masking for common sensitive keys
                if any(
                    word in key.lower()
                    for word in ["password", "key", "token", "secret"]
                ):
                    value = "***MASKED***"
                info["environment"][key] = value

        containers.append(info)

    return containers


def generate_compose(containers):
    """Generate basic docker-compose.yml from containers."""
    compose = {"version": "3.8", "services": {}}

    for container in containers:
        if container["status"] == "running":
            service_name = container["name"].replace("_", "-")
            service = {
                "image": container["image"],
                "container_name": container["name"],
                "restart": "unless-stopped",
            }

            if container["ports"]:
                service["ports"] = container["ports"]

            if container["volumes"]:
                service["volumes"] = container["volumes"]

            # Only add non-masked environment variables
            clean_env = {
                k: v for k, v in container["environment"].items() if v != "***MASKED***"
            }
            if clean_env:
                service["environment"] = clean_env

            compose["services"][service_name] = service

    return compose


def get_system_info():
    """Get basic system information."""
    # Try to get Unraid server hostname from mounted /boot directory
    hostname = "unknown"
    try:
        # Try to get hostname from Unraid boot config
        if Path("/boot/config/ident.cfg").exists():
            with open("/boot/config/ident.cfg") as f:
                for line in f:
                    if line.startswith("NAME="):
                        hostname = line.split("=", 1)[1].strip().strip('"')
                        break
        if hostname == "unknown":
            # Fallback to container hostname
            hostname = subprocess.run(
                ["hostname"], capture_output=True, text=True
            ).stdout.strip()
    except Exception:
        hostname = subprocess.run(
            ["hostname"], capture_output=True, text=True
        ).stdout.strip()

    info = {
        "timestamp": datetime.now().isoformat(),
        "hostname": hostname,
    }

    # Try to get Unraid version from mounted /boot directory
    try:
        if Path("/boot/version").exists():
            info["unraid_version"] = Path("/boot/version").read_text().strip()
        elif Path("/boot/config/version").exists():
            info["unraid_version"] = Path("/boot/config/version").read_text().strip()
        else:
            info["unraid_version"] = "unknown"
    except Exception:
        info["unraid_version"] = "unknown"

    return info


def create_restore_script(system_info):
    """Create simple restoration script."""
    return f"""#!/bin/bash
# Unraid Config Guardian - Restore Script
# Generated: {system_info['timestamp']}
# Server: {system_info['hostname']}

echo "🔄 Restoring Unraid setup..."

# Check prerequisites
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found"
    exit 1
fi

if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found"
    exit 1
fi

# Start containers
echo "📦 Starting containers..."
docker-compose up -d

echo "✅ Restore complete!"
echo "📋 Next steps:"
echo "  1. Restore your appdata from backup"
echo "  2. Check container status: docker-compose ps"
echo "  3. Test your services"
"""


def create_readme(system_info, container_count):
    """Create simple README."""
    return f"""# Unraid Backup Documentation

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Server:** {system_info['hostname']}
**Containers:** {container_count}

## Quick Recovery

1. Install fresh Unraid
2. Restore flash drive from backup
3. Set up disk array
4. Run: `bash restore.sh`
5. Restore appdata from backup

## Files

- `unraid-config.json` - Complete configuration
- `docker-compose.yml` - Container definitions
- `restore.sh` - Restoration script
- `README.md` - This file

## Manual Recovery

```bash
docker-compose up -d
docker-compose ps
```

Keep this documentation safe and test your restore process!
"""


def setup_logging(debug: bool = False, output_dir: str = "/output") -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if debug else logging.INFO

    # Ensure output directory exists
    log_dir = Path(output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Setup handlers
    handlers: List[logging.Handler] = [logging.StreamHandler()]

    # Add file handler if we can write to the directory
    log_file = log_dir / "guardian.log"
    try:
        handlers.append(logging.FileHandler(log_file, mode="a"))
    except (OSError, PermissionError):
        # If we can't write to the specified location, just use console logging
        pass

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Unraid Config Guardian")
    parser.add_argument(
        "--output", default=os.getenv("OUTPUT_DIR", "/output"), help="Output directory"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.debug, args.output)
    logger = logging.getLogger(__name__)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("🚀 Generating Unraid documentation...")

    try:
        # Collect data
        logger.info("📦 Collecting container information...")
        containers = get_containers()

        logger.info("🖥️  Collecting system information...")
        system_info = get_system_info()

        logger.info("📝 Generating docker-compose configuration...")
        compose = generate_compose(containers)

        # Create complete config
        config = {"system_info": system_info, "containers": containers}

        # Write files
        files = {
            "unraid-config.json": json.dumps(config, indent=2),
            "docker-compose.yml": (
                f"# Generated by Config Guardian\n# {system_info['timestamp']}\n\n"
                + yaml.dump(compose, default_flow_style=False)
            ),
            "restore.sh": create_restore_script(system_info),
            "README.md": create_readme(system_info, len(containers)),
        }

        for filename, content in files.items():
            file_path = output_dir / filename
            file_path.write_text(content)
            logger.info(f"✅ Created {filename}")

        # Make restore script executable
        os.chmod(output_dir / "restore.sh", 0o755)

        logger.info(f"🎉 Documentation generated in {output_dir}")
        logger.info(f"📦 Found {len(containers)} containers")

    except Exception as e:
        logger.error(f"❌ Error generating documentation: {str(e)}")
        raise


if __name__ == "__main__":
    main()
