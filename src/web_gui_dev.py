#!/usr/bin/env python3
"""
Development version of Web GUI that handles Docker connection gracefully
"""

import asyncio
import json
import os
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
            {"progress": 50, "message": "Collecting system information..."}
        )

        await asyncio.sleep(1)
        background_status.update(
            {"progress": 75, "message": "Generating docker-compose..."}
        )

        await asyncio.sleep(1)
        background_status.update({"progress": 90, "message": "Writing backup files..."})

        # Create mock backup files
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True, mode=0o755)
        # Set permissions explicitly for Unraid compatibility
        os.chmod(output_path, 0o755)

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
echo "🔄 Restoring Unraid setup..."
docker-compose up -d
echo "✅ Restore complete!"
""",
            "README.md": """# Unraid Backup Documentation

**Generated:** Mock Development Data
**Server:** unraid-server
**Containers:** 3

## Quick Recovery

1. Install fresh Unraid
2. Restore flash drive from backup
3. Set up disk array
4. Run: `bash restore.sh`
5. Restore appdata from backup
""",
        }

        for filename, content in files.items():
            (output_path / filename).write_text(content)

        background_status.update(
            {
                "running": False,
                "progress": 100,
                "message": f"Mock backup completed! Generated {len(files)} files.",
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
