from __future__ import annotations

import random

from app.drivers.base import BaseDriver
from app.models import PortStatus, SwitchCredentials, SwitchStatus, VlanStatus


class MockS2500Driver(BaseDriver):
    """Mock driver that returns realistic fake data for development."""

    def __init__(self, credentials: SwitchCredentials):
        super().__init__(credentials)
        self._connected = False
        self._command_log: list[str] = []

    def connect(self):
        self._connected = True

    def disconnect(self):
        self._connected = False

    def get_status(self) -> SwitchStatus:
        return SwitchStatus(
            hostname="homelab-s2500",
            model="Aruba S2500-48P",
            version="7.4.1.8",
            uptime="45 days, 12:34:56",
            serial="SG12ABC345",
            ports=self.get_port_status(),
            vlans=self.get_vlans(),
        )

    def get_vlans(self) -> list[VlanStatus]:
        return [
            VlanStatus(id=1, name="default", status="active"),
            VlanStatus(id=10, name="management", status="active"),
            VlanStatus(id=20, name="servers", status="active"),
            VlanStatus(id=30, name="workstations", status="active"),
            VlanStatus(id=40, name="voip", status="active"),
            VlanStatus(id=100, name="iot", status="active"),
            VlanStatus(id=200, name="guest", status="active"),
        ]

    def get_port_status(self) -> dict[str, PortStatus]:
        ports: dict[str, PortStatus] = {}
        random.seed(42)  # Deterministic fake data

        # Port definitions matching switch.example.yaml patterns
        port_defs = {
            # Trunk ports - servers
            "1": ("Proxmox Node 1 - Bond Member 1", "trunk", True, False, "1000", "full"),
            "2": ("Proxmox Node 1 - Bond Member 2", "trunk", True, False, "1000", "full"),
            "3": ("Proxmox Node 2", "trunk", True, False, "1000", "full"),
            "4": ("Proxmox Node 2", "trunk", True, False, "1000", "full"),
            # Ports 5-9: defaults (access, vlan 1)
            # Ports 10-20: workstations
            # Ports 21-30: VoIP
            # Ports 31-39: disabled
            # Ports 40-45: cameras
            # Ports 46-48: IoT sensors
        }

        for i in range(1, 49):
            port_id = str(i)

            if port_id in port_defs:
                desc, mode, is_up, poe, speed, duplex = port_defs[port_id]
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if is_up else "down",
                    speed=speed,
                    duplex=duplex,
                    vlan="trunk" if mode == "trunk" else "1",
                    description=desc,
                    poe_status="disabled",
                    poe_power_mw=0,
                    mac_addresses=[_random_mac() for _ in range(random.randint(1, 4))],
                )
            elif 5 <= i <= 9:
                # Default ports - mostly down
                up = random.random() < 0.3
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if up else "down",
                    speed="1000" if up else "auto",
                    duplex="full" if up else "auto",
                    vlan="1",
                    description="",
                    poe_status="searching" if not up else "delivering",
                    poe_power_mw=random.uniform(2000, 8000) if up else 0,
                )
            elif 10 <= i <= 20:
                # Workstations
                up = random.random() < 0.7
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if up else "down",
                    speed="1000" if up else "auto",
                    duplex="full" if up else "auto",
                    vlan="30",
                    description="Office workstations",
                    poe_status="delivering" if up else "searching",
                    poe_power_mw=random.uniform(3000, 12000) if up else 0,
                    mac_addresses=[_random_mac()] if up else [],
                )
            elif 21 <= i <= 30:
                # VoIP phones
                up = random.random() < 0.8
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if up else "down",
                    speed="100" if up else "auto",
                    duplex="full" if up else "auto",
                    vlan="40",
                    description="VoIP phones",
                    poe_status="delivering" if up else "searching",
                    poe_power_mw=random.uniform(4000, 7000) if up else 0,
                    mac_addresses=[_random_mac()] if up else [],
                )
            elif 31 <= i <= 39:
                # Disabled ports
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="down",
                    oper_status="down",
                    speed="auto",
                    duplex="auto",
                    vlan="1",
                    description="Reserved - disabled for security",
                    poe_status="disabled",
                    poe_power_mw=0,
                )
            elif 40 <= i <= 45:
                # Cameras
                up = random.random() < 0.9
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if up else "down",
                    speed="100" if up else "auto",
                    duplex="full" if up else "auto",
                    vlan="100",
                    description="Security cameras",
                    poe_status="delivering" if up else "searching",
                    poe_power_mw=random.uniform(8000, 15000) if up else 0,
                    mac_addresses=[_random_mac()] if up else [],
                )
            else:
                # 46-48 IoT sensors
                up = random.random() < 0.6
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if up else "down",
                    speed="100" if up else "auto",
                    duplex="full" if up else "auto",
                    vlan="100",
                    description="IoT sensors",
                    poe_status="delivering" if up else "searching",
                    poe_power_mw=random.uniform(1000, 4000) if up else 0,
                    mac_addresses=[_random_mac()] if up else [],
                )

        # SFP+ uplinks (49-52)
        for i in range(49, 53):
            port_id = str(i)
            if i <= 51:
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="up",
                    oper_status="up" if i <= 51 else "down",
                    speed="10000",
                    duplex="full",
                    vlan="trunk",
                    description=f"SFP+ Uplink {i - 48}",
                    poe_status="disabled",
                    poe_power_mw=0,
                )
            else:
                ports[port_id] = PortStatus(
                    port_id=port_id,
                    admin_status="down",
                    oper_status="down",
                    speed="auto",
                    duplex="auto",
                    vlan="trunk",
                    description="Spare SFP+ - disabled",
                    poe_status="disabled",
                    poe_power_mw=0,
                )

        return ports

    def send_commands(self, commands: list[str]) -> str:
        self._command_log.extend(commands)
        return "\n".join(f"[mock] {cmd}" for cmd in commands)

    def save_config(self):
        self._command_log.append("write memory")

    def get_running_config(self) -> str:
        return (
            "! Aruba S2500 Running Configuration (MOCK)\n"
            "hostname homelab-s2500\n"
            "!\n"
            "vlan 1\n"
            "  name default\n"
            "!\n"
            "vlan 10\n"
            '  name "management"\n'
            "!\n"
            "vlan 20\n"
            '  name "servers"\n'
            "!\n"
            "vlan 30\n"
            '  name "workstations"\n'
            "!\n"
            "vlan 40\n"
            '  name "voip"\n'
            "!\n"
            "vlan 100\n"
            '  name "iot"\n'
            "!\n"
            "vlan 200\n"
            '  name "guest"\n'
            "!\n"
            "interface GE0/0/1\n"
            '  description "Proxmox Node 1 - Bond Member 1"\n'
            "  switchport mode trunk\n"
            "  switchport trunk native vlan 1\n"
            "  switchport trunk allowed vlan 1,10,20,100\n"
            "  no poe\n"
            "  no shutdown\n"
            "!\n"
        )


def _random_mac() -> str:
    """Generate a random MAC address."""
    return ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
