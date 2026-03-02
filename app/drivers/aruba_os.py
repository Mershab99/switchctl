from __future__ import annotations

import os

from netmiko import ConnectHandler

from app.drivers.base import BaseDriver
from app.models import PortStatus, SwitchCredentials, SwitchStatus, VlanStatus

# Number of copper ports per module on the S2500-48P
_COPPER_PORTS = 48


def _interface_to_port_id(interface_name: str) -> str | None:
    """Map ArubaOS interface name to a port ID string.

    GE0/0/X  -> "X"       (copper, 0-47)
    GE0/1/X  -> "48+X"    (SFP+ uplinks)
    MGMT / other -> None  (skipped)
    """
    if interface_name.startswith("GE0/0/"):
        return interface_name.rsplit("/", 1)[-1]
    if interface_name.startswith("GE0/1/"):
        slot_port = int(interface_name.rsplit("/", 1)[-1])
        return str(_COPPER_PORTS + slot_port)
    return None


class S2500Driver(BaseDriver):
    """Real Netmiko driver for Aruba S2500 Mobility Access Switches."""

    def __init__(self, credentials: SwitchCredentials):
        super().__init__(credentials)
        self.connection = None
        self._template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "templates", "textfsm",
        )

    def connect(self):
        device = {
            "device_type": self.credentials.device_type,
            "host": self.credentials.host,
            "username": self.credentials.username,
            "password": self.credentials.password,
            "port": self.credentials.port,
            "global_delay_factor": 2,
        }
        if self.credentials.enable_password:
            device["secret"] = self.credentials.enable_password

        self.connection = ConnectHandler(**device)

        # Enter enable mode if needed
        if not self.connection.check_enable_mode():
            self.connection.enable()

        # Disable paging
        self.connection.send_command("no paging")

    def disconnect(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def get_status(self) -> SwitchStatus:
        version_template = os.path.join(self._template_dir, "aruba_os_show_version.textfsm")
        version_data = self._send(
            "show version",
            use_textfsm=True,
            textfsm_template=version_template,
        )
        vlans = self.get_vlans()
        ports = self.get_port_status()

        hostname = ""
        model = ""
        version = ""
        uptime = ""
        serial = ""

        if isinstance(version_data, list) and version_data:
            v = version_data[0]
            model = v.get("model", "")
            version = v.get("version", "")
            uptime = v.get("uptime", "")

        return SwitchStatus(
            hostname=hostname,
            model=model,
            version=version,
            uptime=uptime,
            serial=serial,
            ports=ports,
            vlans=vlans,
        )

    def get_vlans(self) -> list[VlanStatus]:
        vlan_template = os.path.join(self._template_dir, "aruba_os_show_vlan.textfsm")
        data = self._send(
            "show vlan",
            use_textfsm=True,
            textfsm_template=vlan_template,
        )
        if isinstance(data, str):
            return []
        return [
            VlanStatus(
                id=int(v.get("vlan_id", 0)),
                name=v.get("name", ""),
                status="active",
            )
            for v in data
        ]

    def get_port_status(self) -> dict[str, PortStatus]:
        # Get interface status
        iface_template = os.path.join(self._template_dir, "aruba_os_show_interface_status.textfsm")
        iface_data = self._send(
            "show interface status",
            use_textfsm=True,
            textfsm_template=iface_template,
        )

        # Get PoE status
        poe_template = os.path.join(self._template_dir, "aruba_os_show_poe_interface_brief.textfsm")
        poe_data = self._send(
            "show poe interface brief",
            use_textfsm=True,
            textfsm_template=poe_template,
        )

        # Build PoE lookup by interface name (e.g. "GE0/0/5")
        poe_lookup: dict[str, dict] = {}
        if isinstance(poe_data, list):
            for p in poe_data:
                poe_lookup[p.get("port", "")] = p

        ports: dict[str, PortStatus] = {}
        if isinstance(iface_data, list):
            for iface in iface_data:
                port_name = iface.get("port", "")
                port_id = _interface_to_port_id(port_name)
                if port_id is None:
                    continue  # skip MGMT and unknown interfaces

                status_str = iface.get("status", "down").lower()
                admin = "down" if status_str == "disabled" else "up"
                oper = "up" if status_str == "connected" else "down"

                poe = poe_lookup.get(port_name, {})
                poe_admin = poe.get("admin", "Disable").lower()
                poe_status_raw = poe.get("poe_status", "Off").lower()

                if poe_admin == "disable":
                    poe_status = "disabled"
                elif poe_status_raw == "on":
                    poe_status = "delivering"
                else:
                    poe_status = "searching"

                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status=admin,
                    oper_status=oper,
                    speed=iface.get("speed", "auto"),
                    duplex=iface.get("duplex", "auto"),
                    vlan=iface.get("vlan", ""),
                    description=iface.get("name", ""),
                    poe_status=poe_status,
                    poe_power_mw=float(poe.get("consumption_mw", 0)),
                )

        return ports

    def send_commands(self, commands: list[str]) -> str:
        if not self.connection:
            raise RuntimeError("Not connected")
        output = self.connection.send_config_set(commands)
        return output

    def save_config(self):
        if not self.connection:
            raise RuntimeError("Not connected")
        self.connection.send_command("write memory")

    def get_running_config(self) -> str:
        if not self.connection:
            raise RuntimeError("Not connected")
        return self.connection.send_command("show running-config")

    def _send(self, command: str, **kwargs):
        """Send a command with fallback to raw output if TextFSM fails."""
        if not self.connection:
            raise RuntimeError("Not connected")
        try:
            return self.connection.send_command(command, **kwargs)
        except Exception:
            return self.connection.send_command(command)
