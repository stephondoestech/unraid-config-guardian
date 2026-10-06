#!/usr/bin/env python3
"""
Tests for credential masking of env vars and Unraid XML templates
"""

import sys
import xml.etree.ElementTree as ET
import zipfile

import pytest

sys.path.insert(0, "src")
import masking  # noqa: E402
import unraid_config_guardian as guardian  # noqa: E402

TEMPLATE_XML = """<?xml version="1.0"?>
<Container version="2">
  <Name>binhex-qbittorrentvpn</Name>
  <ExtraParams>--env VPN_PASS=extrasecret -e TZ=UTC</ExtraParams>
  <Config Name="VPN_USER" Target="VPN_USER" Type="Variable">myvpnuser</Config>
  <Config Name="VPN_PASS" Target="VPN_PASS" Type="Variable" Default="dflt">vpnpw</Config>
  <Config Name="WebUI Password" Target="WEBUI_PW" Type="Variable" Mask="true">pw</Config>
  <Config Name="Custom" Target="CUSTOM_THING" Type="Variable" Mask="true">hidden</Config>
  <Config Name="SSH Keys" Target="/config/keys" Type="Path">/mnt/user/appdata/keys</Config>
  <Config Name="Hotkey Port" Target="8080" Type="Port">8080</Config>
  <Config Name="TZ" Target="TZ" Type="Variable">UTC</Config>
</Container>
"""


@pytest.mark.parametrize(
    "key",
    [
        "DB_PASSWORD",
        "API_KEY",
        "AUTH_TOKEN",
        "APP_SECRET",
        "VPN_PASS",
        "VPN_USER",
        "SOCKS_USER",
        "SOCKS_PASS",
        "WEBUI_PASS",
        "RCON_PWD",
        "PASS",
        "MYSQL_PASSWD",
    ],
)
def test_sensitive_keys(key):
    assert masking.is_sensitive_key(key)


@pytest.mark.parametrize(
    "key", ["TZ", "PUID", "BYPASS_CACHE", "COMPASS_URL", "PATH", "WEBUI_PORT"]
)
def test_non_sensitive_keys(key):
    assert not masking.is_sensitive_key(key)


def test_mask_env_flags():
    params = "--env VPN_PASS=abc -e 'API_KEY=xyz' -e TZ=UTC --net=host"
    masked = masking.mask_env_flags(params)
    assert "abc" not in masked
    assert "xyz" not in masked
    assert "TZ=UTC" in masked
    assert "--net=host" in masked


def _write_template(tmp_path, content=TEMPLATE_XML, name="binhex-qbittorrentvpn.xml"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_mask_template_xml(tmp_path):
    root = ET.fromstring(masking.mask_template_xml(_write_template(tmp_path)))
    configs = {c.get("Name"): c for c in root.findall("Config")}

    assert configs["VPN_USER"].text == masking.MASK_VALUE
    assert configs["VPN_PASS"].text == masking.MASK_VALUE
    assert configs["VPN_PASS"].get("Default") == masking.MASK_VALUE
    assert configs["WebUI Password"].text == masking.MASK_VALUE
    assert configs["Custom"].text == masking.MASK_VALUE
    assert "extrasecret" not in root.findtext("ExtraParams")

    assert configs["SSH Keys"].text == "/mnt/user/appdata/keys"
    assert configs["Hotkey Port"].text == "8080"
    assert configs["TZ"].text == "UTC"


def test_mask_template_xml_invalid_returns_none(tmp_path):
    path = _write_template(tmp_path, "<Container><Config>VPN_PASS & broken")
    assert masking.mask_template_xml(path) is None


def test_create_templates_zip_masks_and_skips_invalid(tmp_path):
    good = _write_template(tmp_path)
    bad = _write_template(tmp_path, "<Container>&", name="broken.xml")
    templates = [
        {"name": good.name, "path": str(good)},
        {"name": bad.name, "path": str(bad)},
    ]
    out = tmp_path / "out"
    out.mkdir()

    zip_path = guardian.create_templates_zip(templates, out)

    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == [good.name]
        content = zf.read(good.name).decode()
    assert "vpnpw" not in content
    assert "extrasecret" not in content
    assert "/mnt/user/appdata/keys" in content


def test_mask_cached_templates(tmp_path):
    _write_template(tmp_path)
    _write_template(tmp_path, "<Container>&", name="broken.xml")

    guardian.mask_cached_templates(tmp_path)

    assert not (tmp_path / "broken.xml").exists()
    assert "vpnpw" not in (tmp_path / "binhex-qbittorrentvpn.xml").read_text()


def test_generate_compose_uses_placeholders_for_masked_values():
    containers = [
        {
            "name": "vpn",
            "image": "binhex/arch-qbittorrentvpn",
            "ports": [],
            "volumes": [],
            "environment": {"VPN_PASS": masking.MASK_VALUE, "TZ": "UTC"},
        }
    ]
    env = guardian.generate_compose(containers)["services"]["vpn"]["environment"]
    assert env == {"VPN_PASS": "${VPN_PASS}", "TZ": "UTC"}


def test_restore_script_does_not_overwrite_templates():
    script = guardian.create_restore_script(
        {"timestamp": "2024-01-01T00:00:00", "hostname": "test-server"}
    )
    assert "unzip -n container-templates.zip" in script
    assert "unzip -o" not in script
    assert masking.MASK_VALUE in script


def test_extra_keywords_from_env(monkeypatch):
    assert not masking.is_sensitive_key("RCON_ADMIN")
    monkeypatch.setenv("MASK_EXTRA_KEYWORDS", " rcon , WEBUI_USER,")
    assert masking.is_sensitive_key("RCON_ADMIN")
    assert masking.is_sensitive_key("WEBUI_USER")
    assert masking.is_sensitive_key("VPN_PASS")
    assert not masking.is_sensitive_key("TZ")


@pytest.mark.parametrize(
    "value,expected",
    [(None, True), ("true", True), ("TRUE", True), ("false", False), ("0", False)],
)
def test_masking_enabled(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("MASK_PASSWORDS", raising=False)
    else:
        monkeypatch.setenv("MASK_PASSWORDS", value)
    assert masking.masking_enabled() is expected


def test_get_containers_respects_mask_passwords_false(monkeypatch):
    from unittest.mock import Mock, patch

    monkeypatch.setenv("MASK_PASSWORDS", "false")
    with patch("docker.from_env") as mock_docker:
        container = Mock()
        container.name = "vpn"
        container.image.tags = ["binhex/arch-qbittorrentvpn"]
        container.status = "running"
        container.attrs = {"Config": {"Env": ["VPN_PASS=hunter2", "TZ=UTC"]}}
        mock_docker.return_value.containers.list.return_value = [container]

        env = guardian.get_containers()[0]["environment"]

    assert env == {"VPN_PASS": "hunter2", "TZ": "UTC"}


def test_create_templates_zip_unmasked_when_disabled(tmp_path):
    good = _write_template(tmp_path)
    out = tmp_path / "out"
    out.mkdir()

    zip_path = guardian.create_templates_zip(
        [{"name": good.name, "path": str(good)}], out, mask_passwords=False
    )

    with zipfile.ZipFile(zip_path) as zf:
        assert "vpnpw" in zf.read(good.name).decode()
