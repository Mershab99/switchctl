# Claude Code Implementation Tasks

## Start Here

Use the `DESIGN.md` for full architecture details. This file is a quick task breakdown.

---

## Task 1: Pydantic Models (`app/models.py`)

Create all the data models:

```python
# Core config models
- SwitchCredentials (host, username, password, port, device_type)
- VlanConfig (id, name, description, ip_address, ip_mask)
- PortConfig (enabled, description, mode, access_vlan, trunk_vlans, speed_duplex, poe_enabled, poe_priority)
- SwitchConfig (name, credentials, vlans, port_defaults, ports, uplinks)

# Status models (from switch)
- PortStatus (port_id, admin_status, oper_status, speed, duplex, vlan, poe_status, poe_power_mw, mac_addresses)
- SwitchStatus (hostname, model, version, uptime, ports, vlans)

# Diff models
- ConfigDiff (resource_type, resource_id, action, field, current_value, desired_value, commands)
```

---

## Task 2: Config Loader (`app/config_loader.py`)

```python
def load_config(path: str) -> SwitchConfig:
    """
    - Load YAML file
    - Substitute ${ENV_VAR} patterns with os.environ
    - Expand port ranges: "1-10" -> ["1", "2", ..., "10"]
    - Merge port_defaults with each port config
    - Validate with Pydantic
    """

def expand_port_range(range_str: str) -> list[str]:
    """Handle "1-10" or "1,3,5-8" patterns"""
```

---

## Task 3: Switch Driver (`app/drivers/aruba_os.py`)

**Key Insight: Use TextFSM for Structured Output!**

Netmiko + ntc-templates gives us parsed data automatically - no regex needed:

```python
# OLD WAY (raw string, needs manual parsing):
raw = conn.send_command("show vlan")
# "VLAN  Name      Status...\n1     default   Port-based..."

# NEW WAY (returns list of dicts!):
parsed = conn.send_command("show vlan", use_textfsm=True)
# [{"vlan_id": "1", "name": "default", "status": "Port-based"}, ...]
```

**Built-in aruba_os templates (ntc-templates):**
| Command | Status |
|---------|--------|
| `show version` | ✅ Built-in |
| `show vlan` | ✅ Built-in |
| `show arp` | ✅ Built-in |
| `show ip interface brief` | ✅ Built-in |
| `show inventory` | ✅ Built-in |
| `show hostname` | ✅ Built-in |

**Need custom templates for:**
- `show interface status` → port grid view
- `show poe interface all` → PoE status
- `show mac-address-table` → connected devices

**Driver Implementation:**

```python
class S2500Driver:
    def __init__(self, credentials: SwitchCredentials)
    def connect(self) -> bool
    def disconnect(self)
    
    # Read operations - USE use_textfsm=True!
    def get_version(self) -> list[dict]:
        return self.conn.send_command("show version", use_textfsm=True)
    
    def get_vlans(self) -> list[dict]:
        return self.conn.send_command("show vlan", use_textfsm=True)
    
    def get_port_status(self) -> list[dict]:
        # Custom template for this command
        return self.conn.send_command(
            "show interface status",
            use_textfsm=True,
            textfsm_template="templates/textfsm/aruba_os_show_interface_status.textfsm"
        )
    
    def get_poe_status(self) -> list[dict]:
        return self.conn.send_command(
            "show poe interface all",
            use_textfsm=True,
            textfsm_template="templates/textfsm/aruba_os_show_poe_interface_all.textfsm"
        )
    
    # Write operations  
    def configure_vlan(self, vlan: VlanConfig) -> str
    def configure_port(self, port_id: str, config: PortConfig) -> str
    def send_commands(self, commands: list[str]) -> str
    def save_config(self) -> str
```

**Custom TextFSM Template Example:**

Create `templates/textfsm/aruba_os_show_interface_status.textfsm`:
```
Value PORT (\S+)
Value NAME (.*)
Value STATUS (up|down|disabled)
Value VLAN (\d+|trunk)
Value DUPLEX (full|half|auto)
Value SPEED (\d+|auto)

Start
  ^${PORT}\s+${NAME}\s+${STATUS}\s+${VLAN}\s+${DUPLEX}\s+${SPEED} -> Record
```

**Important**: Use `device_type="aruba_os"` for Netmiko. The S2500 runs ArubaOS (same as wireless controllers), NOT AOS-Switch.

Also create `MockS2500Driver` that returns fake data for testing.

---

## Task 4: Diff Engine (`app/core/diff.py`)

```python
def diff_config(desired: SwitchConfig, current: SwitchStatus) -> list[ConfigDiff]:
    """Compare desired YAML state vs current switch state"""
    
def generate_commands(diffs: list[ConfigDiff]) -> list[str]:
    """Convert diffs to CLI commands"""
```

---

## Task 5: FastAPI Web App (`app/web/main.py`)

Routes:
- `GET /` - Dashboard
- `GET /ports` - Port grid view
- `GET /ports/{id}` - Port detail (HTMX partial)
- `GET /vlans` - VLAN list
- `GET /diff` - Show planned changes
- `POST /apply` - Apply config
- `GET /api/status` - JSON API

Use HTMX for interactivity without heavy JavaScript.

---

## Task 6: Port Grid Template

Create a visual representation of the 48-port switch:

```
Ports 1-24 (top row, odd numbers)
Ports 1-24 (bottom row, even numbers)
Ports 25-48 (top row, odd numbers)
Ports 25-48 (bottom row, even numbers)
SFP+ ports 49-52
```

Color coding:
- 🟢 Green: Link up
- ⚫ Gray: Link down
- 🔴 Red: Disabled
- Blue glow: PoE active

---

## Task 7: CLI Tool (`cli.py`)

```bash
# Using Typer
./cli.py status           # Show switch status
./cli.py status --json    # JSON output
./cli.py diff             # Show what would change
./cli.py apply            # Apply changes
./cli.py apply --save     # Apply and write memory
./cli.py backup           # Download running-config
```

---

## Testing Without a Switch

Set `MOCK_SWITCH=1` environment variable to use MockDriver:

```bash
MOCK_SWITCH=1 python cli.py status
MOCK_SWITCH=1 uvicorn app.web.main:app --reload
```

---

## Key Netmiko Notes for S2500

```python
# Connection
device = {
    "device_type": "aruba_os",  # NOT "aruba_osswitch"!
    "host": "192.168.1.10",
    "username": "admin", 
    "password": "password",
    "global_delay_factor": 2,  # ArubaOS can be slow
}

# May need to handle enable mode
conn = ConnectHandler(**device)
if not conn.check_enable_mode():
    conn.enable()

# Disable paging
conn.send_command("no paging")

# STRUCTURED OUTPUT - The Key Feature!
# Use use_textfsm=True to get parsed data:
vlans = conn.send_command("show vlan", use_textfsm=True)
# Returns: [{"vlan_id": "1", "name": "default"}, ...]

# For custom templates:
ports = conn.send_command(
    "show interface status",
    use_textfsm=True,
    textfsm_template="path/to/template.textfsm"
)

# Alternative: TTP parser (simpler syntax)
ports = conn.send_command(
    "show interface status",
    use_ttp=True,
    ttp_template="path/to/template.ttp"
)
```

---

## Port Naming Discovery

First thing to do with a real switch - figure out port naming:

```python
# Run these commands and check output format:
conn.send_command("show interface status")
conn.send_command("show interface ?")  # See available interfaces
```

Might be: `GE0/0/1`, `1/0/1`, `Gi1`, or just `1`. Update models accordingly.

---

## Task 8: Create Custom TextFSM Templates

Since ntc-templates doesn't have all S2500 commands, create custom templates.

**Location:** `templates/textfsm/`

**Template 1: `aruba_os_show_interface_status.textfsm`**

First, SSH into switch and capture raw output:
```
Switch# show interface status
Port    Name                  Status    Vlan  Duplex  Speed
------- --------------------- --------- ----- ------- -------
GE0/0/1 Server1               up        10    full    1000
GE0/0/2                       down      1     auto    auto
...
```

Then create template:
```
Value PORT (\S+)
Value NAME (\S*)
Value STATUS (up|down|disabled|notconnect)
Value VLAN (\d+|trunk)
Value DUPLEX (full|half|auto|a-full|a-half)
Value SPEED (\d+|auto)

Start
  ^${PORT}\s+${NAME}\s+${STATUS}\s+${VLAN}\s+${DUPLEX}\s+${SPEED} -> Record
  ^${PORT}\s+${STATUS}\s+${VLAN}\s+${DUPLEX}\s+${SPEED} -> Record
```

**Template 2: `aruba_os_show_poe_interface_all.textfsm`**

```
Value PORT (\S+)
Value POE_STATUS (Delivering|Searching|Disabled|Fault)
Value POWER_MW (\d+\.?\d*)
Value PRIORITY (low|high|critical)
Value CLASS (\d+)

Start
  ^${PORT}\s+${POE_STATUS}\s+${POWER_MW}\s+${PRIORITY}\s+${CLASS} -> Record
```

**Testing templates:**

```python
from ntc_templates.parse import parse_output

raw_output = """your captured output here"""

# Test with ntc_templates directly
result = parse_output(
    platform="aruba_os",
    command="show interface status", 
    data=raw_output
)
print(result)
```

**Pro tip:** Use https://textfsm.nornir.tech/ to test templates interactively!
