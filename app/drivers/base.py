from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import SwitchCredentials, SwitchStatus, PortStatus, VlanStatus


class BaseDriver(ABC):
    """Abstract base class for switch drivers."""

    def __init__(self, credentials: SwitchCredentials):
        self.credentials = credentials

    @abstractmethod
    def connect(self):
        ...

    @abstractmethod
    def disconnect(self):
        ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    @abstractmethod
    def get_status(self) -> SwitchStatus:
        ...

    @abstractmethod
    def get_vlans(self) -> list[VlanStatus]:
        ...

    @abstractmethod
    def get_port_status(self) -> dict[str, PortStatus]:
        ...

    @abstractmethod
    def send_commands(self, commands: list[str]) -> str:
        ...

    @abstractmethod
    def save_config(self):
        ...

    @abstractmethod
    def get_running_config(self) -> str:
        ...
