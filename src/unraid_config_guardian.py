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
from config_diff import create_change_log
from version import __version__

# Removed unused imports: Any, Dict, List


def get_containers():
    """Get all Docker containers and their info."""
    try:
        # For local testing/CI, use direct Docker socket; for production, use proxy
        if os.getenv("PYTEST_CURRENT_TEST") or not os.getenv("DOCKER_HOST"):
            # Local testing - use direct Docker socket
            client = docker.from_env()
        else:
            # Production - use Docker Socket Proxy
            docker_host = os.getenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
            client = docker.DockerClient(base_url=docker_host)

        # Test Docker connectivity
        client.ping()
    except Exception as e:
        logging.error(f"Cannot connect to Docker daemon: {e}")
        logging.error("Make sure Docker Socket Proxy is running and accessible")
        docker_host_env = os.getenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
        logging.error(f"Current DOCKER_HOST: {docker_host_env}")
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
    """Get basic system information using cached boot data when available."""
    # Get hostname with cached data first, then fallbacks
    hostname = "unknown"
    try:
        # Strategy 1: Use cached hostname from entrypoint (preferred)
        cached_hostname = os.environ.get("CACHED_HOSTNAME")
        if cached_hostname:
            hostname = cached_hostname
            logging.info(f"Using cached hostname: {hostname}")
        # Strategy 2: Try direct boot config access (fallback)
        elif Path("/boot/config/ident.cfg").exists():
            with open("/boot/config/ident.cfg") as f:
                for line in f:
                    if line.startswith("NAME="):
                        hostname = line.split("=", 1)[1].strip().strip('"')
                        break
        # Strategy 3: Try hostname command
        if hostname == "unknown":
            result = subprocess.run(["hostname"], capture_output=True, text=True)
            hostname = result.stdout.strip() or "unknown"
    except Exception:
        try:
            result = subprocess.run(["hostname"], capture_output=True, text=True)
            hostname = result.stdout.strip() or "unknown"
        except Exception:
            hostname = "unknown"

    info = {
        "timestamp": datetime.now().isoformat(),
        "hostname": hostname,
        "guardian_version": __version__,
    }

    # Get Unraid version with cached data first, then fallbacks
    unraid_version = "unknown"
    try:
        # Strategy 1: Use cached version from entrypoint (preferred)
        cached_version = os.environ.get("CACHED_UNRAID_VERSION")
        if cached_version:
            unraid_version = cached_version
            logging.info(f"Using cached Unraid version: {unraid_version}")
        # Strategy 2: Try direct boot file access (fallback)
        elif Path("/boot/changes.txt").exists():
            with open("/boot/changes.txt") as f:
                first_line = f.readline().strip()
                # Extract version from "# Version 7.1.4 2025-06-18" format
                if first_line.startswith("# Version "):
                    version_part = first_line.replace("# Version ", "").split()[0]
                    unraid_version = version_part
                    logging.info(f"Found Unraid version: {unraid_version}")

        # Strategy 3: Try alternative version file locations
        if unraid_version == "unknown" and Path("/boot/config/docker.cfg").exists():
            # Sometimes version info is in docker.cfg
            with open("/boot/config/docker.cfg") as f:
                content = f.read()
                if "DOCKER_ENABLED" in content:
                    logging.info("Detected Unraid system (docker.cfg found)")
                    unraid_version = (
                        "Unraid (version detection from /boot/changes.txt failed)"
                    )

        if unraid_version == "unknown":
            logging.warning("/boot directory not mounted or accessible")

    except Exception as e:
        logging.warning(f"Error reading Unraid version: {e}")
        unraid_version = "unknown"

    info["unraid_version"] = unraid_version

    return info


def get_container_templates():
    """Get XML templates from Unraid's template directory."""
    templates = []

    # Refresh cached templates before collection
    # Try multiple approaches for running the refresh with elevated privileges
    refresh_methods = [
        # Method 1: Try sudo (current approach)
        ["sudo", "/usr/local/bin/refresh-templates.sh"],
        # Method 2: Try running directly via docker exec (if available)
        [
            "docker",
            "exec",
            "--user",
            "root",
            os.environ.get("HOSTNAME", "unraid-config-guardian"),
            "/usr/local/bin/refresh-templates.sh",
        ],
        # Method 3: Direct execution (if script is setuid or we have perms)
        ["/usr/local/bin/refresh-templates.sh"],
    ]

    refresh_script = Path("/usr/local/bin/refresh-templates.sh")
    if refresh_script.exists():
        refresh_success = False
        for i, method in enumerate(refresh_methods, 1):
            try:
                logging.info(
                    f"Attempting template refresh method {i}: {' '.join(method[:2])}..."
                )
                result = subprocess.run(
                    method,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logging.info(
                        f"Template cache refreshed successfully using method {i}"
                    )
                    refresh_success = True
                    break
                else:
                    logging.debug(f"Method {i} failed: {result.stderr}")
            except FileNotFoundError:
                logging.debug(f"Method {i} tool not available")
                continue
            except Exception as e:
                logging.debug(f"Method {i} error: {e}")
                continue

        if not refresh_success:
            logging.warning(
                "All template refresh methods failed - attempting entrypoint template caching"
            )
            # Try to run the template caching portion of entrypoint.sh as root
            try:
                entrypoint_template_cache_script = """
                #!/bin/bash
                # Cache template directory accessibility and copy templates (from entrypoint.sh)
                if [ -d "/boot/config/plugins/dockerMan/templates-user" ]; then
                    echo "Template directory accessible"

                    # Create cache directory for templates in /output (persistent location)
                    mkdir -p /output/cached-templates

                    # Copy all XML templates to cache directory (as root, so we can read them)
                    if [ "$(ls -A /boot/config/plugins/dockerMan/templates-user/*.xml \\
                        2>/dev/null)" ]; then
                        cp /boot/config/plugins/dockerMan/templates-user/*.xml \\
                            /output/cached-templates/ 2>/dev/null || true
                        template_count=$(ls -1 /output/cached-templates/*.xml 2>/dev/null | wc -l)
                        echo "Cached $template_count XML templates"
                    else
                        echo "No XML templates found in templates-user directory"
                    fi
                else
                    echo "Template directory not accessible"
                fi
                """

                result = subprocess.run(
                    ["sudo", "bash", "-c", entrypoint_template_cache_script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    logging.info(
                        "Successfully refreshed template cache using entrypoint logic"
                    )
                    # Check if we actually got templates
                    cached_dir = Path("/output/cached-templates")
                    if cached_dir.exists() and list(cached_dir.glob("*.xml")):
                        logging.info("Template cache now contains XML files")
                    else:
                        logging.info("Template cache created but no XML files found")
                else:
                    logging.warning(
                        f"Entrypoint template caching failed: {result.stderr}"
                    )

            except Exception as e:
                logging.warning(f"Could not run entrypoint template caching: {e}")

    # Use cached templates directory (standard location in /output)
    cached_templates_dir = Path("/output/cached-templates")
    if cached_templates_dir.exists():
        template_dir = cached_templates_dir
        logging.info(f"Using cached templates from: {template_dir}")
    else:
        # Fallback to direct access (may fail due to permissions)
        template_dir = Path("/boot/config/plugins/dockerMan/templates-user")
        logging.info("Using direct template directory access")

    if not template_dir.exists():
        logging.info("Template directory not found - no user templates to backup")
        return templates

    logging.info(f"Scanning for XML files in: {template_dir}")

    try:
        xml_files = list(template_dir.glob("*.xml"))
        logging.info(f"Found {len(xml_files)} XML files")

        for xml_file in xml_files:
            if xml_file.is_file():
                templates.append(
                    {
                        "name": xml_file.name,
                        "path": str(xml_file),
                        "size": xml_file.stat().st_size,
                    }
                )
                logging.info(f"Added template: {xml_file.name}")
    except Exception as e:
        logging.error(f"Error scanning templates directory: {e}")

    logging.info(f"Total templates collected: {len(templates)}")
    return templates


def create_templates_zip(templates, output_dir):
    """Create a zip file containing all XML templates."""
    if not templates:
        logging.info("No templates provided for zip creation")
        return None

    zip_path = output_dir / "container-templates.zip"

    logging.info(f"Creating template zip at: {zip_path}")
    logging.info(f"Templates to zip: {len(templates)}")

    templates_added = 0

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for template in templates:
                template_path = Path(template["path"])
                logging.info(
                    f"Processing template: {template['name']} at {template_path}"
                )

                if template_path.exists():
                    try:
                        zipf.write(template_path, template["name"])
                        templates_added += 1
                        logging.info(f"Added {template['name']} to zip")
                    except Exception as template_error:
                        logging.error(
                            f"Failed to add {template['name']}: {template_error}"
                        )
                else:
                    logging.warning(f"Template file not found: {template_path}")

        if templates_added > 0:
            logging.info(
                f"Created templates zip: {zip_path} with {templates_added} templates"
            )

            # Clean up cached templates after successful zip creation
            # Only remove cached templates if we can access the direct boot config path
            try:
                cached_dir = Path("/output/cached-templates")
                boot_templates_dir = Path(
                    "/boot/config/plugins/dockerMan/templates-user"
                )

                if cached_dir.exists():
                    # Test if we can access the boot config directory before cleaning up cache
                    try:
                        if boot_templates_dir.exists() and list(
                            boot_templates_dir.glob("*.xml")
                        ):
                            import shutil

                            shutil.rmtree(cached_dir)
                            logging.info(
                                "Cleaned up cached templates directory - boot config accessible"
                            )
                        else:
                            logging.info(
                                "Keeping cached templates - boot config not accessible"
                            )
                    except (PermissionError, OSError):
                        logging.info(
                            "Keeping cached templates - no permission to access boot config"
                        )
                else:
                    logging.info("No cached templates directory to clean up")
            except Exception as cleanup_error:
                logging.warning(f"Could not clean up cached templates: {cleanup_error}")

            return zip_path
        else:
            logging.error("No templates were successfully added to zip")
            # Remove empty zip file
            if zip_path.exists():
                zip_path.unlink()
            return None

    except Exception as e:
        logging.error(f"Error creating templates zip: {e}")
        logging.error(f"Exception type: {type(e).__name__}")
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
            echo "💡 Install with: curl -L 'https://github.com/docker/compose/releases/" \
                 "latest/download/docker-compose-$(uname -s)-$(uname -m)' " \
                 "-o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose"
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
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    # Set permissions explicitly for Unraid compatibility
    os.chmod(log_dir, 0o755)

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
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    # Set permissions explicitly for Unraid compatibility
    os.chmod(output_dir, 0o755)

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

        # Generate change log (compare with previous backup)
        change_log = create_change_log(output_dir, config)

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

        # Log change summary
        if change_log:
            logger.info("📋 Change log generated - see changes.log for details")
        else:
            logger.info("📋 First backup - no changes to compare")

    except Exception as e:
        logger.error(f"❌ Error generating documentation: {str(e)}")
        raise


if __name__ == "__main__":
    main()
