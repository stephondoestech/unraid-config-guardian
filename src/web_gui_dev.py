#!/usr/bin/env python3
"""
Development version of Web GUI that handles Docker connection gracefully
"""

import asyncio
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Import version info
from version import __version__

# Mock container data for development when Docker isn't available
MOCK_CONTAINERS = [
    {
        "name": "plex",
        "image": "lscr.io/linuxserver/plex:latest",
        "status": "running",
        "ports": ["32400:32400/tcp"],
        "volumes": ["/mnt/user/appdata/plex:/config", "/mnt/user/media:/media"],
        "environment": {"PUID": "99", "PGID": "100", "VERSION": "docker"},
    },
    {
        "name": "nginx",
        "image": "nginx:latest",
        "status": "running",
        "ports": ["80:80/tcp", "443:443/tcp"],
        "volumes": ["/mnt/user/appdata/nginx:/etc/nginx"],
        "environment": {"TZ": "America/New_York"},
    },
    {
        "name": "unifi-controller",
        "image": "lscr.io/linuxserver/unifi-controller:latest",
        "status": "exited",
        "ports": ["8080:8080/tcp", "8443:8443/tcp"],
        "volumes": ["/mnt/user/appdata/unifi:/config"],
        "environment": {"PUID": "99", "PGID": "100", "MONGO_PASSWORD": "***MASKED***"},
    },
]

MOCK_SYSTEM_INFO = {
    "timestamp": datetime.now().isoformat(),
    "hostname": "unraid-server",
    "unraid_version": "6.12.4",
    "guardian_version": __version__,
}

app = FastAPI(
    title="Unraid Config Guardian",
    description="Disaster recovery documentation for Unraid servers",
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Global state for background tasks
background_status = {
    "running": False,
    "progress": 0,
    "message": "Ready",
    "last_run": None,
    "last_error": None,
}


def get_containers_safe():
    """Get containers with fallback to mock data."""
    try:
        # Try to import and use real Docker client
        from unraid_config_guardian import get_containers

        return get_containers()
    except Exception as e:
        print(f"Docker not available, using mock data: {e}")
        return MOCK_CONTAINERS


def get_system_info_safe():
    """Get system info with fallback to mock data."""
    try:
        from unraid_config_guardian import get_system_info

        return get_system_info()
    except Exception:
        return MOCK_SYSTEM_INFO


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard."""
    try:
        system_info = get_system_info_safe()
        containers = get_containers_safe()

        stats = {
            "total_containers": len(containers),
            "running_containers": len(
                [c for c in containers if c["status"] == "running"]
            ),
            "system_info": system_info,
            "last_backup": get_last_backup_info(),
            "status": background_status,
        }
    except Exception as e:
        stats = {"error": str(e), "status": background_status}

    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "stats": stats}
    )


@app.get("/containers", response_class=HTMLResponse)
async def containers_page(request: Request):
    """Containers overview page."""
    try:
        containers = get_containers_safe()
        stats = {"system_info": MOCK_SYSTEM_INFO}
        return templates.TemplateResponse(
            "containers.html",
            {"request": request, "containers": containers, "stats": stats},
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}
        )


@app.get("/api/containers")
async def api_containers():
    """API endpoint for container data."""
    try:
        containers = get_containers_safe()
        return {"containers": containers}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/backup/start")
async def start_backup(
    background_tasks: BackgroundTasks, output_dir: str = Form("/output")
):
    """Start backup process."""
    if background_status["running"]:
        return JSONResponse(
            status_code=409, content={"error": "Backup already running"}
        )

    background_tasks.add_task(run_backup_mock, output_dir)
    return {"message": "Backup started", "status": "running"}


@app.get("/api/backup/status")
async def backup_status():
    """Get backup status."""
    return background_status


@app.get("/api/system")
async def api_system():
    """API endpoint for system information."""
    try:
        system_info = get_system_info_safe()
        return {"system": system_info}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/backups")
async def list_backups(request: Request):
    """List available backups."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    backups = []

    if output_dir.exists():
        for item in output_dir.iterdir():
            if item.is_file() and item.suffix in [".json", ".yml", ".sh", ".md"]:
                backups.append(
                    {
                        "name": item.name,
                        "size": item.stat().st_size,
                        "modified": datetime.fromtimestamp(item.stat().st_mtime),
                        "path": str(item),
                    }
                )

    backups.sort(key=lambda x: x["modified"], reverse=True)  # type: ignore

    stats = {"system_info": MOCK_SYSTEM_INFO}

    return templates.TemplateResponse(
        "backups.html", {"request": request, "backups": backups, "stats": stats}
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download backup file."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    file_path = output_dir / filename

    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, filename=filename)

    return JSONResponse(status_code=404, content={"error": "File not found"})


@app.get("/download-all")
async def download_all_files():
    """Download all backup files as a zip."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))

    # Define the backup files to include
    backup_files = [
        "unraid-config.json",
        "docker-compose.yml",
        "restore.sh",
        "README.md",
        "container-templates.zip",
    ]

    # Check if any backup files exist
    existing_files = [f for f in backup_files if (output_dir / f).exists()]

    if not existing_files:
        return JSONResponse(status_code=404, content={"error": "No backup files found"})

    # Create temporary zip file
    import tempfile

    temp_dir = Path(tempfile.gettempdir())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"unraid-backup_{timestamp}.zip"
    zip_path = temp_dir / zip_filename

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for filename in existing_files:
                file_path = output_dir / filename
                if file_path.exists():
                    zipf.write(file_path, filename)

        return FileResponse(
            zip_path, filename=zip_filename, media_type="application/zip"
        )
    except Exception as e:
        # Clean up on error
        if zip_path.exists():
            zip_path.unlink()
        return JSONResponse(
            status_code=500, content={"error": f"Failed to create zip: {str(e)}"}
        )


async def run_backup_mock(output_dir: str):
    """Mock backup process for development."""

    background_status.update(
        {
            "running": True,
            "progress": 0,
            "message": "Starting backup...",
            "last_error": None,
        }
    )

    try:
        # Simulate backup process
        await asyncio.sleep(1)
        background_status.update(
            {"progress": 25, "message": "Collecting container information..."}
        )

        await asyncio.sleep(1)
        background_status.update(
            {"progress": 40, "message": "Collecting system information..."}
        )

        await asyncio.sleep(1)
        background_status.update(
            {"progress": 60, "message": "Collecting XML templates..."}
        )

        await asyncio.sleep(1)
        background_status.update(
            {"progress": 80, "message": "Generating docker-compose..."}
        )

        await asyncio.sleep(1)
        background_status.update({"progress": 90, "message": "Writing backup files..."})

        # Create mock backup files
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Mock files
        files = {
            "unraid-config.json": json.dumps(
                {"system_info": MOCK_SYSTEM_INFO, "containers": MOCK_CONTAINERS},
                indent=2,
            ),
            "docker-compose.yml": """# Generated by Unraid Config Guardian
version: '3.8'

services:
  plex:
    image: lscr.io/linuxserver/plex:latest
    container_name: plex
    restart: unless-stopped
    ports:
      - "32400:32400"
    volumes:
      - /mnt/user/appdata/plex:/config
      - /mnt/user/media:/media
    environment:
      - PUID=99
      - PGID=100
""",
            "restore.sh": """#!/bin/bash
# Unraid Config Guardian - Restore Script (Mock Development Version)

echo "🔄 Restoring Unraid setup..."

# Function to restore XML templates
restore_templates() {
    if [ -f "container-templates.zip" ]; then
        echo "📋 Restoring XML templates..."
        mkdir -p /boot/config/plugins/dockerMan/templates-user
        unzip -o container-templates.zip -d /boot/config/plugins/dockerMan/templates-user
        if [ $? -eq 0 ]; then
            echo "✅ XML templates restored"
            echo "ℹ️  Templates will appear in 'Add Container' dropdown"
        else
            echo "❌ Failed to extract templates"
        fi
    else
        echo "ℹ️  No container-templates.zip found - skipping template restore"
    fi
}

# Main restore process
echo "📋 UNRAID RESTORE OPTIONS:"
echo "Option 1: Restore XML Templates (Recommended)"
restore_templates

echo ""
echo "Option 2: Docker-Compose Fallback (Emergency only)"
if [ -f "docker-compose.yml" ]; then
    if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
        echo "💡 Run: docker-compose up -d (or docker compose up -d)"
    else
        echo "❌ Docker Compose not available"
    fi
fi

echo ""
echo "✅ Restore process complete!"
echo "📋 Next: Go to Docker tab → Add Container → Select templates"
""",
            "README.md": """# Unraid Backup Documentation

**Generated:** Mock Development Data  
**Server:** unraid-server
**Containers:** 3

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
```
Note: Bypasses Unraid's container management system.

Keep this documentation safe and test your restore process!
""",
        }

        for filename, content in files.items():
            (output_path / filename).write_text(content)

        # Create a mock container-templates.zip with sample XML templates
        template_zip_path = output_path / "container-templates.zip"
        try:
            with zipfile.ZipFile(template_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Mock Plex template
                plex_template = """<?xml version="1.0"?>
<Container version="2">
  <Name>plex</Name>
  <Repository>lscr.io/linuxserver/plex:latest</Repository>
  <Registry>https://lscr.io</Registry>
  <Network>bridge</Network>
  <MyIP/>
  <Shell>bash</Shell>
  <Privileged>false</Privileged>
  <Support>https://forums.unraid.net/topic/40463-support-linuxserver-io-plex-media-server/</Support>
  <Project>https://www.plex.tv/</Project>
  <Overview>Plex organizes video, music and photos from personal media libraries.</Overview>
  <Category>MediaServer:Video MediaServer:Music MediaServer:Photos</Category>
  <WebUI>http://[IP]:[PORT:32400]/web</WebUI>
  <TemplateURL>https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/plex.xml</TemplateURL>
  <Icon>https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/plex-icon.png</Icon>
  <ExtraParams/>
  <PostArgs/>
  <CPUset/>
  <DateInstalled>1640995200</DateInstalled>
  <DonateText>Donations</DonateText>
  <DonateLink>https://www.linuxserver.io/donate</DonateLink>
  <Requires/>
  <Config Name="WebUI" Target="32400" Default="32400" Mode="tcp" Description="Container Port: 32400" Type="Port" Display="always" Required="true" Mask="false">32400</Config>
  <Config Name="Plex Media Server" Target="32400" Default="32400" Mode="tcp" Description="Container Port: 32400" Type="Port" Display="always" Required="true" Mask="false">32400</Config>
  <Config Name="AppData Config Path" Target="/config" Default="/mnt/user/appdata/plex" Mode="rw" Description="Container Path: /config" Type="Path" Display="advanced" Required="true" Mask="false">/mnt/user/appdata/plex</Config>
  <Config Name="Media" Target="/media" Default="/mnt/user/media" Mode="rw" Description="Container Path: /media" Type="Path" Display="always" Required="true" Mask="false">/mnt/user/media</Config>
  <Config Name="PUID" Target="PUID" Default="99" Mode="" Description="Container Variable: PUID" Type="Variable" Display="advanced" Required="true" Mask="false">99</Config>
  <Config Name="PGID" Target="PGID" Default="100" Mode="" Description="Container Variable: PGID" Type="Variable" Display="advanced" Required="true" Mask="false">100</Config>
  <Config Name="VERSION" Target="VERSION" Default="docker" Mode="" Description="Container Variable: VERSION" Type="Variable" Display="advanced" Required="false" Mask="false">docker</Config>
</Container>"""
                zipf.writestr("plex.xml", plex_template)

                # Mock Nginx template
                nginx_template = """<?xml version="1.0"?>
<Container version="2">
  <Name>nginx</Name>
  <Repository>nginx:latest</Repository>
  <Registry>https://hub.docker.com</Registry>
  <Network>bridge</Network>
  <MyIP/>
  <Shell>bash</Shell>
  <Privileged>false</Privileged>
  <Support>https://forums.unraid.net/</Support>
  <Project>https://nginx.org/</Project>
  <Overview>Nginx web server</Overview>
  <Category>Network:Web</Category>
  <WebUI>http://[IP]:[PORT:80]/</WebUI>
  <Icon>https://raw.githubusercontent.com/A75G/docker-templates/master/templates/icons/nginx.png</Icon>
  <Config Name="WebUI" Target="80" Default="8080" Mode="tcp" Description="Container Port: 80" Type="Port" Display="always" Required="true" Mask="false">8080</Config>
  <Config Name="AppData Config Path" Target="/etc/nginx" Default="/mnt/user/appdata/nginx" Mode="rw" Description="Container Path: /etc/nginx" Type="Path" Display="advanced" Required="true" Mask="false">/mnt/user/appdata/nginx</Config>
</Container>"""
                zipf.writestr("nginx.xml", nginx_template)

            file_count = len(files) + 1  # Include the zip file
        except Exception as e:
            print(f"Failed to create mock template zip: {e}")
            file_count = len(files)

        background_status.update(
            {
                "running": False,
                "progress": 100,
                "message": f"Mock backup completed! Generated {file_count} files.",
                "last_run": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        background_status.update(
            {
                "running": False,
                "progress": 0,
                "message": "Backup failed",
                "last_error": str(e),
            }
        )


def get_last_backup_info():
    """Get information about the last backup."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    config_file = output_dir / "unraid-config.json"

    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
            return {
                "timestamp": config.get("system_info", {}).get("timestamp"),
                "containers": len(config.get("containers", [])),
                "size": config_file.stat().st_size,
            }
        except Exception:
            pass

    return None


def main():
    """Run the web server."""
    port = int(os.getenv("WEB_PORT", 7842))
    host = os.getenv("WEB_HOST", "0.0.0.0")

    print("🌐 Starting Unraid Config Guardian Web GUI (Development Mode)")
    print(f"🔗 Access via: http://localhost:{port}")
    print("📋 Note: Using mock data for development")

    uvicorn.run("web_gui_dev:app", host=host, port=port, reload=False, access_log=True)


if __name__ == "__main__":
    main()
