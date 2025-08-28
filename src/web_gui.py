#!/usr/bin/env python3
"""
Web GUI for Unraid Config Guardian
FastAPI-based web interface for managing backups
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Import our main application
from unraid_config_guardian import get_containers, get_system_info, generate_compose, create_restore_script, create_readme


app = FastAPI(title="Unraid Config Guardian", description="Disaster recovery documentation for Unraid servers")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Global state for background tasks
background_status = {
    "running": False,
    "progress": 0,
    "message": "Ready",
    "last_run": None,
    "last_error": None
}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard."""
    # Get basic system info
    try:
        system_info = get_system_info()
        containers = get_containers()
        
        stats = {
            "total_containers": len(containers),
            "running_containers": len([c for c in containers if c["status"] == "running"]),
            "system_info": system_info,
            "last_backup": get_last_backup_info(),
            "status": background_status
        }
    except Exception as e:
        stats = {
            "error": str(e),
            "status": background_status
        }
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats
    })


@app.get("/containers", response_class=HTMLResponse)
async def containers_page(request: Request):
    """Containers overview page."""
    try:
        containers = get_containers()
        return templates.TemplateResponse("containers.html", {
            "request": request,
            "containers": containers
        })
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })


@app.get("/api/containers")
async def api_containers():
    """API endpoint for container data."""
    try:
        containers = get_containers()
        return {"containers": containers}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/backup/start")
async def start_backup(background_tasks: BackgroundTasks, output_dir: str = Form("/output")):
    """Start backup process."""
    if background_status["running"]:
        return JSONResponse(status_code=409, content={"error": "Backup already running"})
    
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
        system_info = get_system_info()
        return {"system": system_info}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/backups")
async def list_backups(request: Request):
    """List available backups."""
    output_dir = Path(os.getenv('OUTPUT_DIR', '/output'))
    backups = []
    
    if output_dir.exists():
        for item in output_dir.iterdir():
            if item.is_file() and item.suffix in ['.json', '.yml', '.sh', '.md']:
                backups.append({
                    "name": item.name,
                    "size": item.stat().st_size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime),
                    "path": str(item)
                })
    
    backups.sort(key=lambda x: x["modified"], reverse=True)
    
    return templates.TemplateResponse("backups.html", {
        "request": request,
        "backups": backups
    })


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download backup file."""
    output_dir = Path(os.getenv('OUTPUT_DIR', '/output'))
    file_path = output_dir / filename
    
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, filename=filename)
    
    return JSONResponse(status_code=404, content={"error": "File not found"})


async def run_backup(output_dir: str):
    """Run backup in background."""
    global background_status
    
    background_status.update({
        "running": True,
        "progress": 0,
        "message": "Starting backup...",
        "last_error": None
    })
    
    try:
        # Step 1: Collect containers
        background_status.update({"progress": 25, "message": "Collecting container information..."})
        containers = get_containers()
        
        # Step 2: Get system info
        background_status.update({"progress": 50, "message": "Collecting system information..."})
        system_info = get_system_info()
        
        # Step 3: Generate compose
        background_status.update({"progress": 75, "message": "Generating docker-compose..."})
        compose = generate_compose(containers)
        
        # Step 4: Write files
        background_status.update({"progress": 90, "message": "Writing backup files..."})
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create complete config
        config = {
            'system_info': system_info,
            'containers': containers
        }
        
        # Write files
        files = {
            'unraid-config.json': json.dumps(config, indent=2),
            'docker-compose.yml': f"# Generated by Unraid Config Guardian\n# {system_info['timestamp']}\n\n" + 
                                 "# TODO: Add proper YAML generation here",
            'restore.sh': create_restore_script(system_info),
            'README.md': create_readme(system_info, len(containers))
        }
        
        for filename, content in files.items():
            (output_path / filename).write_text(content)
        
        # Make restore script executable
        os.chmod(output_path / 'restore.sh', 0o755)
        
        background_status.update({
            "running": False,
            "progress": 100,
            "message": f"Backup completed! Generated {len(files)} files.",
            "last_run": datetime.now().isoformat()
        })
        
    except Exception as e:
        background_status.update({
            "running": False,
            "progress": 0,
            "message": "Backup failed",
            "last_error": str(e)
        })


def get_last_backup_info():
    """Get information about the last backup."""
    output_dir = Path(os.getenv('OUTPUT_DIR', '/output'))
    config_file = output_dir / 'unraid-config.json'
    
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
            return {
                "timestamp": config.get("system_info", {}).get("timestamp"),
                "containers": len(config.get("containers", [])),
                "size": config_file.stat().st_size
            }
        except:
            pass
    
    return None


def main():
    """Run the web server."""
    port = int(os.getenv('WEB_PORT', 8080))
    host = os.getenv('WEB_HOST', '0.0.0.0')
    
    print(f"🌐 Starting Unraid Config Guardian Web GUI on http://{host}:{port}")
    print(f"🔗 Access via: http://your-unraid-ip:7842")
    
    uvicorn.run(
        "web_gui:app",
        host=host,
        port=port,
        reload=False,
        access_log=True
    )


if __name__ == "__main__":
    main()