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
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

import yaml

import docker
from version import __version__

# Removed unused imports: Any, Dict, List


def get_containers():
    """Get all Docker containers and their info."""
    try:
        client = docker.from_env()
        # Test Docker connectivity
        client.ping()
    except Exception as e:
        logging.error(f"Cannot connect to Docker daemon: {e}")
        logging.error("Make sure Docker is running and the socket is accessible")
        logging.error("For Unraid: Ensure container has access to /var/run/docker.sock")
        raise

    containers = []

    for container in client.containers.list(all=True):
        # Extract basic info
        try:
            # Try to get image info, handle missing images gracefully
            image_name = "unknown"
            try:
                if container.image and container.image.tags:
                    image_name = container.image.tags[0]
                elif hasattr(container, "attrs") and container.attrs.get(
                    "Config", {}
                ).get("Image"):
                    # Fallback to image name from container config
                    image_name = container.attrs["Config"]["Image"]
            except (
                docker.errors.ImageNotFound,
                docker.errors.NotFound,
                AttributeError,
            ):
                # Image was deleted or not found, try to get from container attrs
                if hasattr(container, "attrs") and container.attrs.get(
                    "Config", {}
                ).get("Image"):
                    image_name = container.attrs["Config"]["Image"]
                else:
                    image_name = f"missing-image-{container.id[:12]}"

            info = {
                "name": container.name,
                "image": image_name,
                "status": container.status,
                "ports": [],
                "volumes": [],
                "environment": {},
            }
        except Exception as e:
            logging.warning(f"Error processing container {container.name}: {e}")
            continue

        # Get ports
        try:
            ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
            for container_port, host_bindings in ports.items():
                if host_bindings:
                    host_port = host_bindings[0]["HostPort"]
                    info["ports"].append(f"{host_port}:{container_port}")
        except (KeyError, AttributeError, IndexError) as e:
            logging.warning(f"Error getting ports for {container.name}: {e}")

        # Get volumes
        try:
            for mount in container.attrs.get("Mounts") or []:
                if mount.get("Type") == "bind":
                    source = mount.get("Source", "unknown")
                    destination = mount.get("Destination", "unknown")
                    info["volumes"].append(f"{source}:{destination}")
        except (KeyError, AttributeError) as e:
            logging.warning(f"Error getting volumes for {container.name}: {e}")

        # Get environment (mask sensitive data)
        try:
            env_vars = container.attrs.get("Config", {}).get("Env") or []
            for env_var in env_vars:
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    # Simple masking for common sensitive keys
                    if any(
                        word in key.lower()
                        for word in ["password", "key", "token", "secret"]
                    ):
                        value = "***MASKED***"
                    info["environment"][key] = value
        except (KeyError, AttributeError) as e:
            logging.warning(f"Error getting environment for {container.name}: {e}")

        containers.append(info)

    return containers


def generate_compose(containers):
    """Generate basic docker-compose.yml from containers."""
    compose = {"version": "3.8", "services": {}}

    for container in containers:
        # Include all containers regardless of status
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
        "guardian_version": __version__,
    }

    # Try to get Unraid version from mounted /boot directory
    try:
        if Path("/boot/changes.txt").exists():
            with open("/boot/changes.txt") as f:
                first_line = f.readline().strip()
                # Extract version from "# Version 7.1.4 2025-06-18" format
                if first_line.startswith("# Version "):
                    version_part = first_line.replace("# Version ", "").split()[0]
                    info["unraid_version"] = version_part
                else:
                    info["unraid_version"] = "unknown"
        else:
            info["unraid_version"] = "unknown"
    except Exception:
        info["unraid_version"] = "unknown"

    return info


def get_container_templates():
    """Get XML templates from Unraid's template directory."""
    templates = []
    template_dir = Path("/boot/config/plugins/dockerMan/templates-user")

    if not template_dir.exists():
        logging.info("Template directory not found - no user templates to backup")
        return templates

    try:
        for xml_file in template_dir.glob("*.xml"):
            if xml_file.is_file():
                templates.append(
                    {
                        "name": xml_file.name,
                        "path": str(xml_file),
                        "size": xml_file.stat().st_size,
                    }
                )
                logging.info(f"Found template: {xml_file.name}")
    except Exception as e:
        logging.warning(f"Error scanning templates directory: {e}")

    return templates


def create_templates_zip(templates, output_dir):
    """Create a zip file containing all XML templates."""
    if not templates:
        return None

    zip_path = output_dir / "container-templates.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for template in templates:
                template_path = Path(template["path"])
                if template_path.exists():
                    zipf.write(template_path, template["name"])

        logging.info(f"Created templates zip: {zip_path}")
        return zip_path
    except Exception as e:
        logging.error(f"Error creating templates zip: {e}")
        return None


def create_restore_script(system_info):
    """Create restore script for Unraid-native workflow."""
    return f"""#!/bin/bash
# Unraid Config Guardian - Restore Script
# Generated: {system_info['timestamp']}
# Server: {system_info['hostname']}

echo "🔄 Restoring Unraid setup..."

# Function to restore XML templates
restore_templates() {{
    if [ -f "container-templates.zip" ]; then
        echo "📋 Restoring XML templates..."
        
        # Create target directory if it doesn't exist
        mkdir -p /boot/config/plugins/dockerMan/templates-user
        
        # Extract templates
        unzip -o container-templates.zip -d /boot/config/plugins/dockerMan/templates-user
        
        if [ $? -eq 0 ]; then
            echo "✅ XML templates restored to /boot/config/plugins/dockerMan/templates-user"
            echo "ℹ️  Templates will appear in 'Add Container' dropdown"
        else
            echo "❌ Failed to extract templates"
        fi
    else
        echo "ℹ️  No container-templates.zip found - skipping template restore"
    fi
}}

# Function to attempt docker-compose restore (fallback option)
restore_with_compose() {{
    if [ -f "docker-compose.yml" ]; then
        echo ""
        echo "🐳 Attempting docker-compose restore (fallback method)..."
        
        if command -v docker-compose &> /dev/null; then
            docker-compose up -d
            echo "✅ Containers started with docker-compose"
        elif docker compose version &> /dev/null; then
            docker compose up -d  
            echo "✅ Containers started with docker compose"
        else
            echo "❌ Docker Compose not available"
            echo "💡 Install with: curl -L 'https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)' -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose"
            return 1
        fi
    fi
}}

# Main restore process
echo "📋 UNRAID RESTORE OPTIONS:"
echo ""
echo "Option 1: Restore XML Templates (Recommended)"
restore_templates

echo ""
echo "Option 2: Docker-Compose Fallback (Emergency only)"
if restore_with_compose; then
    echo "⚠️  Warning: These containers bypass Unraid's management system"
fi

echo ""
echo "✅ Restore process complete!"
echo ""
echo "📋 NEXT STEPS:"
echo "  1. Go to Docker tab in Unraid WebUI"
echo "  2. Click 'Add Container'"  
echo "  3. Select your templates from 'Template' dropdown"
echo "  4. Configure paths/settings as needed"
echo "  5. Restore appdata from backup"
echo ""
echo "💡 TIPS:"
echo "  - Enable 'Template Authoring Mode' in Docker settings for full template access"
echo "  - Use unraid-config.json for reference settings"
echo "  - Templates provide better integration than docker-compose"
echo "  - Templates support Unraid's auto-start, updates, and management features"
"""


def create_readme(system_info, container_count):
    """Create simple README."""
    return f"""# Unraid Backup Documentation

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Server:** {system_info['hostname']}
**Containers:** {container_count}

## Quick Recovery (Recommended: Unraid Templates)

1. Install fresh Unraid
2. Restore flash drive from backup
3. Set up disk array
4. Run: `bash restore.sh` (restores XML templates)
5. Go to Docker tab → Add Container → Select your templates
6. Configure paths and restore appdata from backup

## Files

- `unraid-config.json` - Complete system configuration
- `container-templates.zip` - XML templates for native Unraid restore
- `docker-compose.yml` - Fallback container definitions  
- `restore.sh` - Automated restoration script
- `README.md` - This file

## Restore Methods

### Method 1: Native Unraid Templates (Recommended)
```bash
bash restore.sh  # Extracts templates to /boot/config/plugins/dockerMan/templates-user
```
Then use Unraid WebUI to add containers from templates.

### Method 2: Docker Compose (Emergency Fallback)
```bash
docker-compose up -d  # Or: docker compose up -d
docker-compose ps
```
Note: Bypasses Unraid's container management system.

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

        logger.info("📋 Collecting XML templates...")
        templates = get_container_templates()

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

        # Create templates zip if templates exist
        if templates:
            logger.info("📦 Creating container templates zip...")
            create_templates_zip(templates, output_dir)
            logger.info(f"✅ Found {len(templates)} XML templates")
        else:
            logger.info("ℹ️  No XML templates found to backup")

        logger.info(f"🎉 Documentation generated in {output_dir}")
        logger.info(f"📦 Found {len(containers)} containers")

    except Exception as e:
        logger.error(f"❌ Error generating documentation: {str(e)}")
        raise


if __name__ == "__main__":
    main()
