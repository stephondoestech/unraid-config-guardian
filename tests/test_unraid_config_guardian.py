#!/usr/bin/env python3
"""
Simple tests for Unraid Config Guardian
"""

import json

# Import the module to test
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, "src")
import unraid_config_guardian as guardian


def test_get_containers():
    """Test container information extraction."""
    with patch("docker.from_env") as mock_docker:
        # Mock container
        mock_container = Mock()
        mock_container.name = "test-container"
        mock_container.image.tags = ["nginx:latest"]
        mock_container.status = "running"
        mock_container.attrs = {
            "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "8080"}]}},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/host/path",
                    "Destination": "/container/path",
                }
            ],
            "Config": {"Env": ["TEST_VAR=test_value", "SECRET_PASSWORD=hidden"]},
        }

        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_docker.return_value = mock_client

        containers = guardian.get_containers()

        assert len(containers) == 1
        container = containers[0]
        assert container["name"] == "test-container"
        assert container["image"] == "nginx:latest"
        assert container["status"] == "running"
        assert "8080:80/tcp" in container["ports"]
        assert "/host/path:/container/path" in container["volumes"]
        assert container["environment"]["SECRET_PASSWORD"] == "***MASKED***"


def test_generate_compose():
    """Test docker-compose generation."""
    containers = [
        {
            "name": "test-app",
            "image": "nginx:latest",
            "status": "running",
            "ports": ["8080:80/tcp"],
            "volumes": ["/host:/container"],
            "environment": {"ENV": "prod"},
        }
    ]

    compose = guardian.generate_compose(containers)

    assert compose["version"] == "3.8"
    assert "test-app" in compose["services"]
    service = compose["services"]["test-app"]
    assert service["image"] == "nginx:latest"
    assert service["restart"] == "unless-stopped"
    assert "8080:80/tcp" in service["ports"]


@patch("subprocess.run")
def test_get_system_info(mock_subprocess):
    """Test system information gathering."""
    mock_subprocess.return_value.stdout = "unraid-server"

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "read_text", return_value="6.12.4"):
            info = guardian.get_system_info()

            assert info["hostname"] == "unraid-server"
            assert info["unraid_version"] == "6.12.4"
            assert "timestamp" in info


def test_create_restore_script():
    """Test restoration script creation."""
    system_info = {"timestamp": "2024-01-01T00:00:00", "hostname": "test-server"}

    script = guardian.create_restore_script(system_info)

    assert "#!/bin/bash" in script
    assert "test-server" in script
    assert "docker-compose up -d" in script


def test_create_readme():
    """Test README creation."""
    system_info = {"hostname": "test-server"}

    readme = guardian.create_readme(system_info, 5)

    assert "# Unraid Backup Documentation" in readme
    assert "test-server" in readme
    assert "Containers: 5" in readme


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
