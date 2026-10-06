#!/usr/bin/env python3
"""
Tests for web GUI Docker error handling
"""

import sys
from unittest.mock import Mock, PropertyMock, patch

import pytest

sys.path.insert(0, "src")
import unraid_config_guardian as guardian  # noqa: E402
import web_gui  # noqa: E402


def test_get_containers_safe_raises_instead_of_mock_data(monkeypatch):
    monkeypatch.setattr(web_gui, "DOCKER_AVAILABLE", True)
    monkeypatch.setenv("DOCKER_HOST", "tcp://192.168.1.50:2375")

    def boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(web_gui, "get_containers", boom)

    with pytest.raises(RuntimeError, match="tcp://192.168.1.50:2375"):
        web_gui.get_containers_safe()


def test_get_containers_when_image_api_forbidden():
    """Socket proxy with IMAGES=0 returns 403 for image lookups."""
    import docker

    with patch("docker.from_env") as mock_docker:
        container = Mock()
        container.name = "sonarr"
        container.status = "running"
        container.attrs = {"Config": {"Image": "lscr.io/linuxserver/sonarr", "Env": []}}
        type(container).image = PropertyMock(
            side_effect=docker.errors.APIError("403 Forbidden")
        )
        mock_docker.return_value.containers.list.return_value = [container]

        containers = guardian.get_containers()

    assert [c["image"] for c in containers] == ["lscr.io/linuxserver/sonarr"]
