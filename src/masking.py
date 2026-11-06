#!/usr/bin/env python3
"""
Credential masking for container environment variables and Unraid XML templates.
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

MASK_VALUE = "***MASKED***"

# Matched anywhere in the variable name (e.g. DB_PASSWORD, API_KEY).
SENSITIVE_SUBSTRINGS = ("password", "passwd", "secret", "token", "key")

# Matched as a whole word in the variable name (e.g. VPN_PASS, RCON_PWD),
# so names like BYPASS_CACHE or COMPASS are left alone.
SENSITIVE_WORDS = {"pass", "pwd", "pw"}

# Usernames that are credentials in practice (binhex VPN containers).
SENSITIVE_NAMES = {"vpn_user", "socks_user"}

MASK_PASSWORDS_ENV = "MASK_PASSWORDS"

# Comma-separated extra keywords, matched anywhere in the name (e.g. "rcon,webui_user").
EXTRA_KEYWORDS_ENV = "MASK_EXTRA_KEYWORDS"

_ENV_FLAG_RE = re.compile(
    r"(?P<flag>(?:-e|--env)[\s=]+)(?P<quote>['\"]?)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s'\"]*)(?P=quote)"
)


def masking_enabled() -> bool:
    """MASK_PASSWORDS toggle; anything other than an explicit false value keeps masking on."""
    value = os.getenv(MASK_PASSWORDS_ENV, "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def extra_keywords() -> List[str]:
    """User-supplied keywords from MASK_EXTRA_KEYWORDS."""
    raw = os.getenv(EXTRA_KEYWORDS_ENV, "")
    return [word.strip().lower() for word in raw.split(",") if word.strip()]


def is_sensitive_key(key: str) -> bool:
    """Return True if an env var / template variable name looks like a credential."""
    lowered = key.lower().strip()
    if not lowered:
        return False
    if lowered in SENSITIVE_NAMES:
        return True
    if any(word in lowered for word in (*SENSITIVE_SUBSTRINGS, *extra_keywords())):
        return True
    return any(word in SENSITIVE_WORDS for word in re.split(r"[^a-z0-9]+", lowered))


def mask_env_flags(params: str) -> str:
    """Mask values of sensitive `-e KEY=value` / `--env KEY=value` flags."""

    def _replace(match: re.Match) -> str:
        if not is_sensitive_key(match.group("key")):
            return str(match.group(0))
        quote = match.group("quote")
        return f"{match.group('flag')}{quote}{match.group('key')}={MASK_VALUE}{quote}"

    return _ENV_FLAG_RE.sub(_replace, params)


def _is_sensitive_config(config: ET.Element) -> bool:
    if (config.get("Mask") or "").lower() == "true":
        return True
    if (config.get("Type") or "Variable") != "Variable":
        return False
    return is_sensitive_key(config.get("Name") or "") or is_sensitive_key(
        config.get("Target") or ""
    )


def mask_template_xml(xml_path: Path) -> Optional[bytes]:
    """Return a masked copy of an Unraid template, or None if it cannot be parsed.

    Only Variable-type configs (or configs Unraid itself flags with Mask="true")
    are masked, so paths, ports and devices stay intact for restore.
    """
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return None

    for config in root.iter("Config"):
        if _is_sensitive_config(config):
            if config.text:
                config.text = MASK_VALUE
            if config.get("Default"):
                config.set("Default", MASK_VALUE)

    for tag in ("ExtraParams", "PostArgs"):
        for element in root.iter(tag):
            if element.text:
                element.text = mask_env_flags(element.text)

    xml_bytes: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes
