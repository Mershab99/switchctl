from __future__ import annotations

from app.config_loader import parse_trunk_allowed_vlans
from app.core.commands import generate_port_commands, generate_vlan_commands
from app.models import (
    ConfigDiff,
    PortConfig,
    PortStatus,
    SwitchConfig,
    SwitchStatus,
    VlanConfig,
    VlanStatus,
)


def diff_vlans(
    desired: list[VlanConfig],
    current: list[VlanStatus],
) -> list[ConfigDiff]:
    """Compare desired VLANs against current VLANs on switch."""
    diffs: list[ConfigDiff] = []

    current_map = {v.id: v for v in current}
    desired_map = {v.id: v for v in desired}

    # VLANs to create
    for vlan in desired:
        if vlan.id not in current_map:
            diff = ConfigDiff(
                resource_type="vlan",
                resource_id=str(vlan.id),
                action="create",
                field="vlan",
                current_value=None,
                desired_value={"id": vlan.id, "name": vlan.name},
            )
            diff.commands = generate_vlan_commands(diff, vlan)
            diffs.append(diff)
        else:
            # Check for name changes
            cur = current_map[vlan.id]
            if cur.name != vlan.name:
                diff = ConfigDiff(
                    resource_type="vlan",
                    resource_id=str(vlan.id),
                    action="update",
                    field="name",
                    current_value=cur.name,
                    desired_value=vlan.name,
                )
                diff.commands = generate_vlan_commands(diff, vlan)
                diffs.append(diff)

    # VLANs to delete (on switch but not in config) - skip default VLAN 1
    for vid, cur in current_map.items():
        if vid not in desired_map and vid != 1:
            diff = ConfigDiff(
                resource_type="vlan",
                resource_id=str(vid),
                action="delete",
                field="vlan",
                current_value={"id": vid, "name": cur.name},
                desired_value=None,
            )
            diff.commands = [f"no vlan {vid}"]
            diffs.append(diff)

    return diffs


def diff_ports(
    desired: dict[str, PortConfig],
    current: dict[str, PortStatus],
) -> list[ConfigDiff]:
    """Compare desired port configs against current port state."""
    diffs: list[ConfigDiff] = []

    for port_id, desired_cfg in desired.items():
        current_port = current.get(port_id)
        if current_port is None:
            continue

        port_diffs = _diff_single_port(port_id, desired_cfg, current_port)
        diffs.extend(port_diffs)

    return diffs


def _diff_single_port(
    port_id: str,
    desired: PortConfig,
    current: PortStatus,
) -> list[ConfigDiff]:
    """Compare a single port's desired config vs current state."""
    diffs: list[ConfigDiff] = []

    # Admin status (enabled/disabled)
    desired_admin = "up" if desired.enabled else "down"
    if current.admin_status != desired_admin:
        diffs.append(ConfigDiff(
            resource_type="port",
            resource_id=port_id,
            action="update",
            field="admin_status",
            current_value=current.admin_status,
            desired_value=desired_admin,
        ))

    # Description
    desired_desc = desired.description or ""
    if current.description != desired_desc:
        diffs.append(ConfigDiff(
            resource_type="port",
            resource_id=port_id,
            action="update",
            field="description",
            current_value=current.description,
            desired_value=desired_desc,
        ))

    # VLAN / mode
    if desired.mode == "access":
        desired_vlan = str(desired.access_vlan) if desired.access_vlan else "1"
        current_vlan = current.vlan or "1"
        if current_vlan != desired_vlan:
            diffs.append(ConfigDiff(
                resource_type="port",
                resource_id=port_id,
                action="update",
                field="access_vlan",
                current_value=current_vlan,
                desired_value=desired_vlan,
            ))
    elif desired.mode == "trunk":
        if current.vlan != "trunk":
            diffs.append(ConfigDiff(
                resource_type="port",
                resource_id=port_id,
                action="update",
                field="mode",
                current_value="access",
                desired_value="trunk",
            ))

    # PoE
    if desired.poe_enabled:
        if current.poe_status == "disabled":
            diffs.append(ConfigDiff(
                resource_type="port",
                resource_id=port_id,
                action="update",
                field="poe_enabled",
                current_value=False,
                desired_value=True,
            ))
    else:
        if current.poe_status not in ("disabled",):
            diffs.append(ConfigDiff(
                resource_type="port",
                resource_id=port_id,
                action="update",
                field="poe_enabled",
                current_value=True,
                desired_value=False,
            ))

    # Generate commands for all port diffs
    if diffs:
        commands = generate_port_commands(port_id, desired)
        for d in diffs:
            d.commands = commands

    return diffs


def diff_config(
    desired: SwitchConfig,
    current: SwitchStatus,
) -> list[ConfigDiff]:
    """Full diff of desired config vs current switch state.

    Returns diffs ordered: VLANs first, then ports.
    """
    diffs: list[ConfigDiff] = []

    # VLAN diffs
    diffs.extend(diff_vlans(desired.vlans, current.vlans))

    # Combine ports and uplinks
    all_desired_ports = dict(desired.ports)
    all_desired_ports.update(desired.uplinks)

    # Port diffs
    diffs.extend(diff_ports(all_desired_ports, current.ports))

    return diffs
