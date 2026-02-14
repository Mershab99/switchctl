from __future__ import annotations

from app.models import ConfigDiff, PortConfig, VlanConfig


def generate_vlan_commands(diff: ConfigDiff, vlan: VlanConfig) -> list[str]:
    """Generate ArubaOS CLI commands for a VLAN diff."""
    commands: list[str] = []

    if diff.action == "delete":
        commands.append(f"no vlan {diff.resource_id}")
        return commands

    commands.append(f"vlan {vlan.id}")
    if vlan.name:
        commands.append(f'  name "{vlan.name}"')
    commands.append("  exit")

    return commands


def generate_port_commands(port_id: str, config: PortConfig) -> list[str]:
    """Generate ArubaOS CLI commands for a port configuration."""
    commands: list[str] = []
    commands.append(f"interface GE0/0/{port_id}")

    if config.description:
        commands.append(f'  description "{config.description}"')

    if config.mode == "access":
        commands.append("  switchport mode access")
        if config.access_vlan:
            commands.append(f"  switchport access vlan {config.access_vlan}")
    elif config.mode == "trunk":
        commands.append("  switchport mode trunk")
        if config.trunk_native_vlan:
            commands.append(f"  switchport trunk native vlan {config.trunk_native_vlan}")
        if config.trunk_allowed_vlans:
            if isinstance(config.trunk_allowed_vlans, list):
                vlan_str = ",".join(str(v) for v in config.trunk_allowed_vlans)
            else:
                vlan_str = str(config.trunk_allowed_vlans)
            commands.append(f"  switchport trunk allowed vlan {vlan_str}")

    if config.speed_duplex and config.speed_duplex != "auto":
        commands.append(f"  speed {config.speed_duplex}")

    if config.poe_enabled:
        commands.append("  poe")
        if config.poe_priority != "low":
            commands.append(f"  poe priority {config.poe_priority}")
    else:
        commands.append("  no poe")

    if config.enabled:
        commands.append("  no shutdown")
    else:
        commands.append("  shutdown")

    commands.append("  exit")

    return commands


def generate_commands(diffs: list[ConfigDiff]) -> list[str]:
    """Collect all commands from diffs in order (VLANs first, then ports)."""
    vlan_cmds: list[str] = []
    port_cmds: list[str] = []

    for diff in diffs:
        if diff.resource_type == "vlan":
            vlan_cmds.extend(diff.commands)
        else:
            port_cmds.extend(diff.commands)

    # Deduplicate port commands (multiple diffs for same port produce
    # identical command blocks — keep only the first occurrence of each block)
    seen_interfaces: set[str] = set()
    deduped: list[str] = []
    skip = False
    for cmd in port_cmds:
        if cmd.startswith("interface "):
            if cmd in seen_interfaces:
                skip = True
                continue
            seen_interfaces.add(cmd)
            skip = False
        if skip:
            continue
        deduped.append(cmd)

    return vlan_cmds + deduped
