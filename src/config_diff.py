#!/usr/bin/env python3
"""
Configuration change tracking for Unraid Config Guardian.

Compares current configuration with previous backups to generate change logs.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_previous_config(output_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Find and load the most recent previous config file.

    Args:
        output_dir: Directory where backups are stored

    Returns:
        Previous config dictionary or None if not found
    """
    config_file = output_dir / "unraid-config.json"

    if not config_file.exists():
        return None

    try:
        with open(config_file, "r") as f:
            config_data: Dict[str, Any] = json.load(f)
            return config_data
    except Exception as e:
        logger.warning(f"Could not read previous config: {e}")
        return None


def compare_containers(
    old_containers: List[Dict], new_containers: List[Dict]
) -> Dict[str, List[str]]:
    """
    Compare container configurations between backups.

    Args:
        old_containers: Previous container configurations
        new_containers: Current container configurations

    Returns:
        Dictionary with added, removed, and modified containers
    """
    old_by_name = {c.get("name", "unknown"): c for c in old_containers}
    new_by_name = {c.get("name", "unknown"): c for c in new_containers}

    old_names = set(old_by_name.keys())
    new_names = set(new_by_name.keys())

    changes: Dict[str, List[str]] = {"added": [], "removed": [], "modified": []}

    # Find added containers
    for name in new_names - old_names:
        container = new_by_name[name]
        image = container.get("image", "unknown")
        changes["added"].append(f"+ {name} (image: {image})")

    # Find removed containers
    for name in old_names - new_names:
        container = old_by_name[name]
        image = container.get("image", "unknown")
        changes["removed"].append(f"- {name} (image: {image})")

    # Find modified containers
    for name in old_names & new_names:
        old_container = old_by_name[name]
        new_container = new_by_name[name]

        container_changes = compare_single_container(old_container, new_container)
        if container_changes:
            changes["modified"].append(f"~ {name}:")
            changes["modified"].extend(
                [f"    {change}" for change in container_changes]
            )

    return changes


def compare_single_container(old: Dict, new: Dict) -> List[str]:
    """
    Compare a single container configuration for changes.

    Args:
        old: Previous container configuration
        new: Current container configuration

    Returns:
        List of change descriptions
    """
    changes = []

    # Compare key fields
    fields_to_compare = [
        ("image", "Image"),
        ("status", "Status"),
        ("restart_policy", "Restart Policy"),
    ]

    for field, display_name in fields_to_compare:
        old_val = old.get(field, "N/A")
        new_val = new.get(field, "N/A")
        if old_val != new_val:
            changes.append(f"{display_name}: {old_val} → {new_val}")

    # Compare ports
    old_ports = set(old.get("ports", []))
    new_ports = set(new.get("ports", []))
    if old_ports != new_ports:
        if old_ports - new_ports:
            changes.append(f"Removed ports: {', '.join(old_ports - new_ports)}")
        if new_ports - old_ports:
            changes.append(f"Added ports: {', '.join(new_ports - old_ports)}")

    # Compare volumes (simplified)
    # Volumes are stored as strings like "/host/path:/container/path"
    old_volumes = set(old.get("volumes", []))
    new_volumes = set(new.get("volumes", []))
    if old_volumes != new_volumes:
        if old_volumes - new_volumes:
            changes.append(f"Removed volumes: {', '.join(old_volumes - new_volumes)}")
        if new_volumes - old_volumes:
            changes.append(f"Added volumes: {', '.join(new_volumes - old_volumes)}")

    # Compare environment variables (count only, not values for security)
    old_env_count = len(old.get("environment", {}))
    new_env_count = len(new.get("environment", {}))
    if old_env_count != new_env_count:
        changes.append(f"Environment variables: {old_env_count} → {new_env_count}")

    return changes


def compare_system_info(old_system: Dict, new_system: Dict) -> List[str]:
    """
    Compare system information for changes.

    Args:
        old_system: Previous system information
        new_system: Current system information

    Returns:
        List of system changes
    """
    changes = []

    # Compare key system fields
    fields_to_compare = [
        ("unraid_version", "Unraid Version"),
        ("hostname", "Hostname"),
        ("kernel_version", "Kernel Version"),
    ]

    for field, display_name in fields_to_compare:
        old_val = old_system.get(field, "N/A")
        new_val = new_system.get(field, "N/A")
        if old_val != new_val:
            changes.append(f"{display_name}: {old_val} → {new_val}")

    # Compare disk array (simplified)
    old_disks = len(old_system.get("disks", []))
    new_disks = len(new_system.get("disks", []))
    if old_disks != new_disks:
        changes.append(f"Disk count: {old_disks} → {new_disks}")

    # Compare shares (simplified)
    old_shares = len(old_system.get("shares", []))
    new_shares = len(new_system.get("shares", []))
    if old_shares != new_shares:
        changes.append(f"Share count: {old_shares} → {new_shares}")

    return changes


def generate_change_log(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> str:
    """
    Generate a human-readable change log comparing two configurations.

    Args:
        old_config: Previous configuration
        new_config: Current configuration

    Returns:
        Formatted change log string
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old_timestamp = old_config.get("system_info", {}).get("timestamp", "Unknown")

    log_lines = [
        "# Unraid Configuration Changes",
        f"Generated: {timestamp}",
        f"Previous backup: {old_timestamp}",
        "",
        "## Summary",
        "",
    ]

    # Compare containers
    container_changes = compare_containers(
        old_config.get("containers", []), new_config.get("containers", [])
    )

    total_changes = (
        len(container_changes["added"])
        + len(container_changes["removed"])
        + len(container_changes["modified"])
    )

    if total_changes == 0:
        log_lines.extend(
            [
                "✅ **No container changes detected**",
                "",
                "All containers remain unchanged since the last backup.",
                "",
            ]
        )
    else:
        log_lines.append(f"📦 **{total_changes} container changes detected**")
        log_lines.append("")

        # Added containers
        if container_changes["added"]:
            log_lines.append("### New Containers")
            log_lines.extend(container_changes["added"])
            log_lines.append("")

        # Removed containers
        if container_changes["removed"]:
            log_lines.append("### Removed Containers")
            log_lines.extend(container_changes["removed"])
            log_lines.append("")

        # Modified containers
        if container_changes["modified"]:
            log_lines.append("### Modified Containers")
            log_lines.extend(container_changes["modified"])
            log_lines.append("")

    # Compare system info
    system_changes = compare_system_info(
        old_config.get("system_info", {}), new_config.get("system_info", {})
    )

    if system_changes:
        log_lines.append("## System Changes")
        log_lines.append("")
        log_lines.extend([f"🖥️  {change}" for change in system_changes])
        log_lines.append("")
    else:
        log_lines.extend(
            ["## System Changes", "", "✅ **No system changes detected**", ""]
        )

    # Footer
    log_lines.extend(["---", "*Generated by Unraid Config Guardian*", ""])

    return "\n".join(log_lines)


def create_change_log(output_dir: Path, new_config: Dict[str, Any]) -> Optional[str]:
    """
    Create a change log file by comparing with the previous backup.

    Args:
        output_dir: Directory where backups are stored
        new_config: Current configuration to compare

    Returns:
        Change log content or None if no previous config exists
    """
    logger.info("🔍 Checking for configuration changes...")

    # Get previous configuration
    old_config = get_previous_config(output_dir)

    changes_file = output_dir / "changes.log"

    if not old_config:
        # First backup - create initial change log
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        container_count = len(new_config.get("containers", []))
        hostname = new_config.get("system_info", {}).get("hostname", "unknown")

        first_backup_log = f"""# Unraid Config Guardian - Change Log

## Initial Backup - {timestamp}

**Server:** {hostname}
**Containers:** {container_count}

This is the first backup for this Unraid server. Future backups will show changes compared to this
baseline.

### Summary
- ✅ Initial configuration captured
- ✅ {container_count} containers documented
- ✅ System information recorded

Future change logs will appear here when configurations are modified.
"""
        changes_file.write_text(first_backup_log)
        logger.info("✅ Initial change log created: changes.log")
        return first_backup_log

    # Generate change log for subsequent backups
    change_log = generate_change_log(old_config, new_config)

    # Write change log file
    changes_file.write_text(change_log)

    logger.info("✅ Change log created: changes.log")

    return change_log
