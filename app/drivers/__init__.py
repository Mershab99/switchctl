import os
from app.models import SwitchCredentials


def get_driver(credentials: SwitchCredentials, mock: bool = False):
    """Factory function to get the appropriate switch driver."""
    if mock or os.environ.get("MOCK_SWITCH", "").strip() == "1":
        from app.drivers.mock import MockS2500Driver
        return MockS2500Driver(credentials)
    else:
        from app.drivers.aruba_os import S2500Driver
        return S2500Driver(credentials)
