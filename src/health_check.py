#!/usr/bin/env python3
"""
Health check script for Unraid Config Guardian container
"""

import sys
import os
import docker
from pathlib import Path


def check_docker_connection():
    """Check if Docker daemon is accessible."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception as e:
        print(f"Docker connection failed: {e}")
        return False


def check_output_directory():
    """Check if output directory is writable."""
    try:
        output_dir = Path(os.getenv('OUTPUT_DIR', '/output'))
        test_file = output_dir / '.health_check'
        test_file.touch()
        test_file.unlink()
        return True
    except Exception as e:
        print(f"Output directory not writable: {e}")
        return False


def check_config_directory():
    """Check if config directory is accessible."""
    try:
        config_dir = Path('/config')
        return config_dir.exists() and config_dir.is_dir()
    except Exception as e:
        print(f"Config directory check failed: {e}")
        return False


def main():
    """Main health check function."""
    checks = [
        ("Docker connection", check_docker_connection),
        ("Output directory", check_output_directory),
        ("Config directory", check_config_directory),
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        try:
            if check_func():
                print(f"✅ {check_name}: OK")
            else:
                print(f"❌ {check_name}: FAILED")
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name}: ERROR - {e}")
            all_passed = False
    
    if all_passed:
        print("🟢 All health checks passed")
        sys.exit(0)
    else:
        print("🔴 One or more health checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()