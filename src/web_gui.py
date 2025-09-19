#!/usr/bin/env python3
"""
Web GUI for Unraid Config Guardian
FastAPI-based web interface for managing backups
"""

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

# Import our main application
try:
    from unraid_config_guardian import (
        create_readme,
        create_restore_script,
        generate_compose,
        get_containers,
        get_system_info,
    )

    DOCKER_AVAILABLE = True
except Exception:
    DOCKER_AVAILABLE = False

app = FastAPI(
    title="Unraid Config Guardian",
    description="Disaster recovery documentation for Unraid servers",
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Mock data for development when Docker isn't available
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
    if not DOCKER_AVAILABLE:
        return MOCK_CONTAINERS
    try:
        return get_containers()
    except Exception as e:
        print(f"Docker not available, using mock data: {e}")
        return MOCK_CONTAINERS


def get_system_info_safe():
    """Get system info with fallback to mock data."""
    if not DOCKER_AVAILABLE:
        return MOCK_SYSTEM_INFO
    try:
        return get_system_info()
    except Exception:
        return MOCK_SYSTEM_INFO


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard."""
    # Get basic system info
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
        system_info = get_system_info_safe()
        stats = {"system_info": system_info}
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

    background_tasks.add_task(run_backup, output_dir)
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
    output_dir = Path(os.getenv("OUTPUT_DIR", "/output"))
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

    system_info = get_system_info_safe()
    stats = {"system_info": system_info}

    return templates.TemplateResponse(
        "backups.html", {"request": request, "backups": backups, "stats": stats}
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download backup file."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "/output"))
    file_path = output_dir / filename

    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, filename=filename)

    return JSONResponse(status_code=404, content={"error": "File not found"})


@app.get("/download-all")
async def download_all_files():
    """Download all backup files as a zip."""
    output_dir = Path(os.getenv("OUTPUT_DIR", "/output"))

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


async def run_backup(output_dir: str):
    """Run backup in background."""
    background_status.update(
        {
            "running": True,
            "progress": 0,
            "message": "Starting backup...",
            "last_error": None,
        }
    )

    try:
        # Step 1: Collect containers
        background_status.update(
            {"progress": 25, "message": "Collecting container information..."}
        )
        containers = get_containers_safe()

        # Step 2: Get system info
        background_status.update(
            {"progress": 50, "message": "Collecting system information..."}
        )
        system_info = get_system_info_safe()

        # Step 3: Generate compose
        background_status.update(
            {"progress": 75, "message": "Generating docker-compose..."}
        )
        if DOCKER_AVAILABLE:
            compose = generate_compose(containers)
        else:
            # Mock compose for development
            compose = {
                "version": "3.8",
                "services": {
                    "plex": {
                        "image": "lscr.io/linuxserver/plex:latest",
                        "container_name": "plex",
                        "restart": "unless-stopped",
                        "ports": ["32400:32400"],
                        "volumes": ["/mnt/user/appdata/plex:/config"],
                        "environment": {"PUID": "99", "PGID": "100"},
                    }
                },
            }

        # Step 4: Collect templates
        background_status.update(
            {"progress": 80, "message": "Collecting XML templates..."}
        )
        templates = []
        if DOCKER_AVAILABLE:
            from unraid_config_guardian import get_container_templates

            templates = get_container_templates()

        # Step 5: Write files
        background_status.update({"progress": 90, "message": "Writing backup files..."})

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True, mode=0o755)
        # Set permissions explicitly for Unraid compatibility
        os.chmod(output_path, 0o755)

        # Create complete config
        config = {
            "system_info": system_info,
            "containers": containers,
            "templates": templates,
        }

        # Write files
        import yaml

        if DOCKER_AVAILABLE:
            restore_script = create_restore_script(system_info)
            readme = create_readme(system_info, len(containers))
        else:
            # Mock scripts for development
            restore_script = """#!/bin/bash
echo "🔄 Restoring Unraid setup (DEVELOPMENT MODE)..."
docker-compose up -d
echo "✅ Restore complete!"
"""
            readme = f"""# Unraid Backup Documentation (DEVELOPMENT MODE)

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Server:** {system_info['hostname']}
**Containers:** {len(containers)}

This is a development/demo backup.
"""

        files = {
            "unraid-config.json": json.dumps(config, indent=2),
            "docker-compose.yml": (
                f"# Generated by Config Guardian\n# {system_info['timestamp']}\n\n"
                + yaml.dump(compose, default_flow_style=False)
            ),
            "restore.sh": restore_script,
            "README.md": readme,
        }

        for filename, content in files.items():
            (output_path / filename).write_text(content)

        # Make restore script executable
        os.chmod(output_path / "restore.sh", 0o755)

        # Create templates zip if templates exist
        if templates and DOCKER_AVAILABLE:
            background_status.update(
                {"progress": 95, "message": "Creating templates zip..."}
            )
            from unraid_config_guardian import create_templates_zip

            zip_result = create_templates_zip(templates, output_path)
            if zip_result:
                files["container-templates.zip"] = "Binary file"

        background_status.update(
            {
                "running": False,
                "progress": 100,
                "message": f"Backup completed! Generated {len(files)} files.",
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
    output_dir = Path(os.getenv("OUTPUT_DIR", "/output"))
    config_file = output_dir / "unraid-config.json"

    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)

            backup_info = {
                "timestamp": config.get("system_info", {}).get("timestamp"),
                "containers": len(config.get("containers", [])),
                "size": config_file.stat().st_size,
                "has_changes": False,
                "changes_summary": "No changes detected",
            }

            # Check for changes.log file
            changes_file = output_dir / "changes.log"
            if changes_file.exists():
                try:
                    changes_content = changes_file.read_text()
                    backup_info["has_changes"] = True

                    # Extract summary from changes file
                    lines = changes_content.split("\n")
                    for line in lines:
                        if "changes detected" in line:
                            backup_info["changes_summary"] = line.strip().replace(
                                "**", ""
                            )
                            break
                    else:
                        backup_info[
                            "changes_summary"
                        ] = "Changes detected - see changes.log"

                except Exception:
                    backup_info[
                        "changes_summary"
                    ] = "Changes file exists but couldn't be read"

            return backup_info
        except Exception:
            pass

    return None


def main():
    """Run the web server."""
    port = int(os.getenv("WEB_PORT", 7842))
    host = os.getenv("WEB_HOST", "0.0.0.0")

    print(f"🌐 Starting Unraid Config Guardian Web GUI on http://{host}:{port}")
    print("🔗 Access via: http://your-unraid-ip:7842")

    uvicorn.run("web_gui:app", host=host, port=port, reload=False, access_log=True)


if __name__ == "__main__":
    main()
