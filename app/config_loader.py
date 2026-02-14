from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from app.models import PortConfig, SwitchConfig


def substitute_env_vars(data):
    """Recursively walk data and replace ${VAR} patterns with env values."""
    if isinstance(data, str):
        def _replace(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(f"Environment variable '{var_name}' is not set")
            return value
        return re.sub(r"\$\{(\w+)\}", _replace, data)
    elif isinstance(data, dict):
        return {k: substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [substitute_env_vars(item) for item in data]
    return data


def expand_port_range(range_str: str) -> list[str]:
    """Expand port range strings into individual port numbers.

    Examples:
        "1-10"     -> ["1", "2", ..., "10"]
        "1,3,5-8"  -> ["1", "3", "5", "6", "7", "8"]
    """
    ports: list[str] = []
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            for i in range(int(start), int(end) + 1):
                ports.append(str(i))
        else:
            ports.append(part)
    return ports


def parse_trunk_allowed_vlans(value) -> list[int]:
    """Parse trunk_allowed_vlans from either list[int] or string format."""
    if isinstance(value, list):
        return [int(v) for v in value]
    if isinstance(value, str):
        vlans: list[int] = []
        for part in value.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                vlans.extend(range(int(start), int(end) + 1))
            else:
                vlans.append(int(part))
        return vlans
    return []


def _is_port_range(key: str) -> bool:
    """Check if a port key represents a range (contains - or , with digits)."""
    return bool(re.match(r"^[\d,\s-]+$", key)) and ("-" in key or "," in key) and not key.isdigit()


def _merge_port_config(defaults: dict | None, override: dict) -> dict:
    """Merge port_defaults with a per-port override."""
    if defaults is None:
        return override
    merged = dict(defaults)
    merged.update({k: v for k, v in override.items() if v is not None})
    return merged


def load_config(path: str | Path = "config/switch.yaml") -> SwitchConfig:
    """Load and validate switch config from YAML.

    Steps:
    1. Load YAML file
    2. Substitute ${ENV_VAR} patterns
    3. Expand port ranges in ports/uplinks
    4. Merge port_defaults with each port config
    5. Validate with Pydantic
    """
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    # Env var substitution (allow missing env vars for credentials gracefully)
    try:
        raw = substitute_env_vars(raw)
    except ValueError:
        # If env vars aren't set, substitute with placeholder for mock mode
        raw["credentials"] = _safe_substitute_credentials(raw.get("credentials", {}))

    # Extract port_defaults as a dict for merging
    port_defaults = raw.get("port_defaults")

    # Expand port ranges and merge defaults
    raw["ports"] = _expand_and_merge(raw.get("ports", {}), port_defaults)
    raw["uplinks"] = _expand_and_merge(raw.get("uplinks", {}), port_defaults)

    # Parse trunk_allowed_vlans for all ports
    for port_cfg in raw["ports"].values():
        if "trunk_allowed_vlans" in port_cfg and port_cfg["trunk_allowed_vlans"] is not None:
            port_cfg["trunk_allowed_vlans"] = parse_trunk_allowed_vlans(
                port_cfg["trunk_allowed_vlans"]
            )
    for port_cfg in raw["uplinks"].values():
        if "trunk_allowed_vlans" in port_cfg and port_cfg["trunk_allowed_vlans"] is not None:
            port_cfg["trunk_allowed_vlans"] = parse_trunk_allowed_vlans(
                port_cfg["trunk_allowed_vlans"]
            )

    return SwitchConfig(**raw)


def _safe_substitute_credentials(creds: dict) -> dict:
    """Substitute env vars in credentials, using placeholders for missing ones."""
    result = {}
    for k, v in creds.items():
        if isinstance(v, str) and "${" in v:
            var_name = re.search(r"\$\{(\w+)\}", v)
            if var_name:
                result[k] = os.environ.get(var_name.group(1), "mock_password")
            else:
                result[k] = v
        else:
            result[k] = v
    return result


def _expand_and_merge(ports_dict: dict, port_defaults: dict | None) -> dict:
    """Expand port ranges and merge with defaults."""
    expanded: dict[str, dict] = {}
    for key, config in ports_dict.items():
        key_str = str(key)
        if _is_port_range(key_str):
            for port_id in expand_port_range(key_str):
                expanded[port_id] = _merge_port_config(port_defaults, config)
        else:
            expanded[key_str] = _merge_port_config(port_defaults, config)
    return expanded
