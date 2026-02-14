from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Config models (from YAML)
# ---------------------------------------------------------------------------

class SwitchCredentials(BaseModel):
    host: str
    username: str
    password: str
    enable_password: Optional[str] = None
    port: int = 22
    device_type: str = "aruba_os"


class VlanConfig(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


class PortConfig(BaseModel):
    enabled: bool = True
    description: Optional[str] = None
    mode: str = "access"  # access | trunk
    access_vlan: Optional[int] = None
    trunk_native_vlan: Optional[int] = None
    trunk_allowed_vlans: Optional[list[int] | str] = None
    speed_duplex: str = "auto"
    poe_enabled: bool = True
    poe_priority: str = "low"  # low | high | critical


class SwitchConfig(BaseModel):
    name: str
    credentials: SwitchCredentials
    vlans: list[VlanConfig] = Field(default_factory=list)
    port_defaults: Optional[PortConfig] = None
    ports: dict[str, PortConfig] = Field(default_factory=dict)
    uplinks: dict[str, PortConfig] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Status models (from switch)
# ---------------------------------------------------------------------------

class PortStatus(BaseModel):
    port_id: str
    admin_status: str = "up"       # up | down
    oper_status: str = "up"        # up | down
    speed: str = "auto"
    duplex: str = "auto"
    vlan: Optional[str] = None
    description: str = ""
    poe_status: str = "disabled"   # delivering | searching | disabled | fault
    poe_power_mw: float = 0.0
    mac_addresses: list[str] = Field(default_factory=list)


class VlanStatus(BaseModel):
    id: int
    name: str
    status: str = "active"


class SwitchStatus(BaseModel):
    hostname: str = ""
    model: str = ""
    version: str = ""
    uptime: str = ""
    serial: str = ""
    ports: dict[str, PortStatus] = Field(default_factory=dict)
    vlans: list[VlanStatus] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Diff model
# ---------------------------------------------------------------------------

class ConfigDiff(BaseModel):
    resource_type: str   # vlan | port
    resource_id: str
    action: str          # create | update | delete
    field: str
    current_value: Any = None
    desired_value: Any = None
    commands: list[str] = Field(default_factory=list)
