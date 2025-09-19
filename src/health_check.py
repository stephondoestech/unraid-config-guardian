#!/usr/bin/env python3
"""
Health check script for Unraid Config Guardian container
"""

import os
import sys
from pathlib import Path


def check_docker_connection():
    """Check if Docker daemon is accessible."""
    try:
        # Use docker.sock directly to avoid import issues during startup
        docker_sock = Path("/var/run/docker.sock")
        if not docker_sock.exists():
            print("Docker socket not found at /var/run/docker.sock")
            return False

        # Try importing docker library
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except ImportError as e:
        print(f"Docker library not available: {e}")
        return False
    except Exception as e:
        print(f"Docker connection failed: {e}")
        return False


def check_output_directory():
    """Check if output directory is writable."""
    try:
        output_dir = Path(os.getenv("OUTPUT_DIR", "/output"))

        # Check if directory exists
        if not output_dir.exists():
            print(f"Output directory does not exist: {output_dir}")
            return False

        # Check if directory is writable (less invasive test)
        if not os.access(output_dir, os.W_OK):
            print(f"Output directory not writable: {output_dir}")
            return False

        # Try to create a test file only if we have write access
        test_file = output_dir / ".health_check"
        try:
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            # Directory exists but no write permission
            print(f"No write permission for output directory: {output_dir}")
            return False

        return True
    except Exception as e:
        print(f"Output directory check failed: {e}")
        return False


def check_config_directory():
    """Check if config directory is accessible."""
    try:
        config_dir = Path("/config")
        if not config_dir.exists():
            print(f"Config directory does not exist: {config_dir}")
            return False
        if not config_dir.is_dir():
            print(f"Config path is not a directory: {config_dir}")
            return False
        return True
    except Exception as e:
        print(f"Config directory check failed: {e}")
        return False


def check_application_files():
    """Check if core application files are accessible."""
    try:
        app_files = [
            Path("/app/src/unraid_config_guardian.py"),
            Path("/app/src/web_gui.py"),
        ]

        for app_file in app_files:
            if not app_file.exists():
                print(f"Core application file missing: {app_file}")
                return False

        return True
    except Exception as e:
        print(f"Application files check failed: {e}")
        return False


def main():
    """Main health check function."""
    print(f"Health check running as user: {os.getuid()}:{os.getgid()}")

    checks = [
        ("Application files", check_application_files),
        ("Config directory", check_config_directory),
        ("Output directory", check_output_directory),
        ("Docker connection", check_docker_connection),
    ]

    all_passed = True
    results = []

    for check_name, check_func in checks:
        try:
            if check_func():
                print(f"✅ {check_name}: OK")
                results.append(f"{check_name}: OK")
            else:
                print(f"❌ {check_name}: FAILED")
                results.append(f"{check_name}: FAILED")
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name}: ERROR - {e}")
            results.append(f"{check_name}: ERROR - {e}")
            all_passed = False

    # Summary
    print("-" * 40)
    for result in results:
        print(f"  {result}")

    if all_passed:
        print("🟢 All health checks passed")
        sys.exit(0)
    else:
        print("🔴 One or more health checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
