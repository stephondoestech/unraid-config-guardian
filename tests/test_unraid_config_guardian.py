#!/usr/bin/env python3
"""
Simple tests for Unraid Config Guardian
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Import the module to test
sys.path.insert(0, "src")
import unraid_config_guardian as guardian  # noqa: E402


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


def test_get_containers_masks_sensitive_env_vars():
    """Test that each sensitive keyword triggers masking of its env var value."""
    with patch("docker.from_env") as mock_docker:
        mock_container = Mock()
        mock_container.name = "test-container"
        mock_container.image.tags = ["nginx:latest"]
        mock_container.status = "running"
        mock_container.attrs = {
            "NetworkSettings": {},
            "Mounts": [],
            "Config": {
                "Env": [
                    "DB_PASSWORD=hunter2",
                    "API_KEY=abc123",
                    "AUTH_TOKEN=xyz789",
                    "APP_SECRET=shh",
                    "VPN_PASS=vpnpass123",
                    "VPN_USER=vpnuser123",
                    "SOCKS_USER=socksuser123",
                    "SOCKS_PASS=sockspass123",
                    "TEST_VAR=not_sensitive",
                ]
            },
        }

        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        mock_docker.return_value = mock_client

        containers = guardian.get_containers()

        assert len(containers) == 1
        env = containers[0]["environment"]

        assert env["DB_PASSWORD"] == "***MASKED***"
        assert env["API_KEY"] == "***MASKED***"
        assert env["AUTH_TOKEN"] == "***MASKED***"
        assert env["APP_SECRET"] == "***MASKED***"
        assert env["VPN_PASS"] == "***MASKED***"
        assert env["VPN_USER"] == "***MASKED***"
        assert env["SOCKS_USER"] == "***MASKED***"
        assert env["SOCKS_PASS"] == "***MASKED***"

        # Sanity check: non-sensitive vars pass through unmasked
        assert env["TEST_VAR"] == "not_sensitive"


def test_mask_template_xml(tmp_path):
    """Test that sensitive Config values in Unraid template XML are masked."""
    import xml.etree.ElementTree as ET

    xml_content = """<?xml version="1.0"?>
<Container version="2">
  <Name>binhex-qbittorrentvpn</Name>
  <Config Name="VPN_USER" Target="VPN_USER" Type="Variable">myvpnuser</Config>
  <Config Name="VPN_PASS" Target="VPN_PASS" Type="Variable">myvpnpass</Config>
  <Config Name="SOCKS_USER" Target="SOCKS_USER" Type="Variable">mysocksuser</Config>
  <Config Name="SOCKS_PASS" Target="SOCKS_PASS" Type="Variable">mysockspass</Config>
  <Config Name="WebUI Port" Target="8080" Type="Port">8080</Config>
</Container>
"""
    template_path = tmp_path / "binhex-qbittorrentvpn.xml"
    template_path.write_text(xml_content, encoding="utf-8")

    masked_xml = guardian.mask_template_xml(template_path)
    root = ET.fromstring(masked_xml)
    configs = {c.get("Name"): c.text for c in root.findall("Config")}

    assert configs["VPN_USER"] == "***MASKED***"
    assert configs["VPN_PASS"] == "***MASKED***"
    assert configs["SOCKS_USER"] == "***MASKED***"
    assert configs["SOCKS_PASS"] == "***MASKED***"

    # Sanity check: non-sensitive config passes through unmasked
    assert configs["WebUI Port"] == "8080"


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
@patch("builtins.open")
def test_get_system_info(mock_open, mock_subprocess):
    """Test system information gathering."""
    mock_subprocess.return_value.stdout = "unraid-server"

    # Mock file contexts with proper enter/exit
    mock_ident_file = Mock()
    mock_ident_file.__enter__ = Mock(return_value=mock_ident_file)
    mock_ident_file.__exit__ = Mock(return_value=None)
    mock_ident_file.__iter__ = Mock(return_value=iter(['NAME="TestServer"\n']))

    mock_changes_file = Mock()
    mock_changes_file.__enter__ = Mock(return_value=mock_changes_file)
    mock_changes_file.__exit__ = Mock(return_value=None)
    mock_changes_file.readline.return_value = "# Version 7.1.4 2025-06-18"

    def open_side_effect(filename, *args, **kwargs):
        if "/boot/config/ident.cfg" in filename:
            return mock_ident_file
        elif "/boot/changes.txt" in filename:
            return mock_changes_file
        return Mock()

    mock_open.side_effect = open_side_effect

    with patch.object(Path, "exists", return_value=True):
        info = guardian.get_system_info()

        assert info["hostname"] == "TestServer"
        assert info["unraid_version"] == "7.1.4"
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
    assert "**Containers:** 5" in readme


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
