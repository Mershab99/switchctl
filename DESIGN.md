# Aruba S2500 Switch Manager - Design Document

## Overview

A Python web application for managing Aruba S2500 Mobility Access Switches with a **declarative YAML configuration** as the source of truth and a web UI layered on top.

---

## Goals

1. **Declarative Config First**: YAML defines desired state, system reconciles
2. **Visual Port View**: See all 48 ports + 4 SFP+ at a glance with status
3. **Safe Operations**: Diff/plan before apply, like Terraform
4. **Offline Capable**: Edit YAML without switch connectivity, apply later

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI (FastAPI + HTMX)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Dashboard│  │Port View │  │VLAN Mgmt │  │ Config Editor    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                      Core Engine                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Config Loader│  │ Diff Engine  │  │ Command Generator      │ │
│  │ (YAML/Pydantic)│ │ (current vs  │  │ (diff → CLI commands)  │ │
│  │              │  │  desired)    │  │                        │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                      Switch Driver                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Netmiko SSH Driver (ArubaOS)                             │   │
│  │ - send_command() for reads                               │   │
│  │ - send_config_set() for writes                           │   │
│  │ - Output parsers (regex-based)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Mock Driver (for development/testing)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Declarative YAML Schema

```yaml
# config/switch.yaml
name: "homelab-s2500"

credentials:
  host: "192.168.1.10"
  username: "admin"
  password: "${SWITCH_PASSWORD}"  # Environment variable substitution
  device_type: "aruba_os"

vlans:
  - id: 1
    name: "default"
  - id: 10
    name: "management"
    description: "Management network"
  - id: 20
    name: "servers"
    description: "Server VLAN"
  - id: 100
    name: "iot"
    description: "IoT devices - isolated"

# Port defaults (applied to all ports unless overridden)
port_defaults:
  enabled: true
  mode: access
  access_vlan: 1
  poe_enabled: true
  poe_priority: low
  speed_duplex: auto

# Port-specific overrides
ports:
  # Single port
  "1":
    description: "Proxmox Node 1 - NIC1"
    mode: trunk
    trunk_native_vlan: 1
    trunk_allowed_vlans: [1, 10, 20, 100]
    poe_enabled: false
  
  # Port range syntax
  "2-4":
    description: "Proxmox Nodes"
    mode: trunk
    trunk_allowed_vlans: "1,10,20,100"
    poe_enabled: false
  
  # Access ports
  "10-20":
    description: "Office workstations"
    mode: access
    access_vlan: 10
  
  # IoT ports with PoE
  "40-48":
    description: "IoT/Camera ports"
    mode: access
    access_vlan: 100
    poe_priority: high
  
  # Disabled ports
  "30-39":
    enabled: false
    description: "Reserved - disabled"

# Uplink ports (SFP+)
uplinks:
  "49":  # or "sfp1" depending on switch notation
    description: "Uplink to Core"
    mode: trunk
    trunk_allowed_vlans: "1-100"
  "50":
    description: "Uplink to Core - redundant"
    mode: trunk
    trunk_allowed_vlans: "1-100"
```

---

## Core Components

### 1. Config Loader (`config/loader.py`)

**Responsibilities:**
- Load YAML files with environment variable substitution
- Validate against Pydantic models
- Expand port ranges ("1-10" → ["1", "2", ..., "10"])
- Merge port_defaults with port-specific configs

**Key Functions:**
```python
def load_config(path: str) -> SwitchConfig
def expand_port_range(range_str: str) -> list[str]
def substitute_env_vars(config: dict) -> dict
```

### 2. Switch Driver (`drivers/aruba_os.py`)

**Responsibilities:**
- SSH connection management via Netmiko
- Execute show commands and parse output
- Execute config commands
- Handle connection errors gracefully

**Key Classes:**
```python
class S2500Driver:
    def connect() -> bool
    def disconnect()
    def get_status() -> SwitchStatus
    def get_port_status(port_id: str) -> PortStatus
    def get_vlans() -> list[VlanConfig]
    def get_running_config() -> str
    def send_commands(commands: list[str]) -> str
    def save_config()
```

**Netmiko device_type**: `aruba_os` (for ArubaOS on S2500)

### 3. Diff Engine (`core/diff.py`)

**Responsibilities:**
- Compare desired config (YAML) vs current state (from switch)
- Generate list of changes needed
- Support dry-run mode

**Key Functions:**
```python
def diff_config(desired: SwitchConfig, current: SwitchStatus) -> list[ConfigDiff]
def diff_vlans(desired: list[VlanConfig], current: list) -> list[ConfigDiff]
def diff_ports(desired: dict[str, PortConfig], current: dict[str, PortStatus]) -> list[ConfigDiff]
```

**ConfigDiff Model:**
```python
@dataclass
class ConfigDiff:
    resource_type: str  # "vlan" | "port"
    resource_id: str    # "10" or "1/0/1"
    action: str         # "create" | "update" | "delete"
    field: str          # "access_vlan" | "description" | etc
    current_value: Any
    desired_value: Any
    commands: list[str] # CLI commands to apply this change
```

### 4. Command Generator (`core/commands.py`)

**Responsibilities:**
- Convert ConfigDiff objects into ArubaOS CLI commands
- Handle command ordering (VLANs before ports)
- Generate rollback commands

**Key Functions:**
```python
def generate_commands(diffs: list[ConfigDiff]) -> list[str]
def generate_vlan_commands(diff: ConfigDiff) -> list[str]
def generate_port_commands(diff: ConfigDiff) -> list[str]
```

### 5. Web UI (`web/`)

**Stack:**
- **FastAPI** - Async web framework
- **HTMX** - Dynamic UI without heavy JS
- **Jinja2** - Templates
- **TailwindCSS** - Styling

**Pages:**

| Route | Description |
|-------|-------------|
| `GET /` | Dashboard - switch status overview |
| `GET /ports` | Visual port grid with status |
| `GET /ports/{id}` | Single port detail/edit modal |
| `GET /vlans` | VLAN list and management |
| `GET /config` | YAML config editor |
| `GET /diff` | Show planned changes |
| `POST /apply` | Apply configuration |
| `GET /api/status` | JSON API for status |

---

## Visual Port View Design

```
┌─────────────────────────────────────────────────────────────────────┐
│  Aruba S2500-48P                          ● Connected   Uptime: 45d │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  FRONT PANEL                                                        │
│  ┌────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┐     │
│  │ 1  │ 3  │ 5  │ 7  │ 9  │ 11 │ 13 │ 15 │ 17 │ 19 │ 21 │ 23 │ ... │
│  ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤     │
│  │ 2  │ 4  │ 6  │ 8  │ 10 │ 12 │ 14 │ 16 │ 18 │ 20 │ 22 │ 24 │ ... │
│  └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘     │
│                                                                     │
│  ┌────┬────┬────┬────┐                                              │
│  │SFP1│SFP2│SFP3│SFP4│  10G Uplinks                                 │
│  └────┴────┴────┴────┘                                              │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Legend:  🟢 Up/Link  🔴 Down  🟡 Disabled  🔵 PoE Active           │
└─────────────────────────────────────────────────────────────────────┘
```

**Port colors:**
- Green: Link up
- Red: Link down (but enabled)
- Gray: Administratively disabled
- Blue border: PoE delivering power
- Orange: Config drift detected

**Click on port → Modal with:**
- Current status (speed, duplex, PoE watts)
- Connected MACs
- Current config
- Edit form
- View in YAML button

---

## Workflow: Apply Configuration

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 1. Load YAML │────▶│ 2. Fetch     │────▶│ 3. Diff      │
│    Config    │     │    Current   │     │    Engine    │
└──────────────┘     │    State     │     └──────┬───────┘
                     └──────────────┘            │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 6. Save      │◀────│ 5. Execute   │◀────│ 4. Generate  │
│    Config    │     │    Commands  │     │    Commands  │
└──────────────┘     └──────────────┘     └──────────────┘
```

**CLI equivalent:**
```bash
# Show what would change
./switchctl diff

# Apply changes
./switchctl apply

# Apply with auto-save
./switchctl apply --save
```

---

## File Structure

```
switch-manager/
├── config/
│   ├── switch.yaml          # Main switch config
│   └── switch.example.yaml  # Example template
├── templates/
│   └── textfsm/             # Custom TextFSM templates
│       ├── aruba_os_show_interface_status.textfsm
│       ├── aruba_os_show_poe_interface_all.textfsm
│       └── aruba_os_show_mac-address-table.textfsm
├── app/
│   ├── __init__.py
│   ├── models.py            # Pydantic models
│   ├── config_loader.py     # YAML loading & validation
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract base driver
│   │   ├── aruba_os.py      # S2500 driver (uses TextFSM)
│   │   └── mock.py          # Mock for testing
│   ├── core/
│   │   ├── __init__.py
│   │   ├── diff.py          # Diff engine
│   │   └── commands.py      # Command generator
│   └── web/
│       ├── __init__.py
│       ├── main.py          # FastAPI app
│       ├── routes/
│       │   ├── dashboard.py
│       │   ├── ports.py
│       │   ├── vlans.py
│       │   └── api.py
│       ├── templates/
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── ports.html
│       │   ├── port_detail.html
│       │   └── vlans.html
│       └── static/
│           ├── css/
│           └── js/
├── cli.py                   # CLI tool (switchctl)
├── requirements.txt
├── Dockerfile
├── docker-compose.yaml
└── README.md
```

---

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| SSH Library | Netmiko | Best network device support, handles ArubaOS quirks |
| **Output Parsing** | **TextFSM + ntc-templates** | **Pre-built templates, structured data from CLI** |
| Web Framework | FastAPI | Async, fast, auto OpenAPI docs |
| Frontend | HTMX + Jinja2 | Simple, no build step, great for this use case |
| Styling | TailwindCSS (CDN) | Quick styling, no build step |
| Config Format | YAML + Pydantic | Human readable, validated, typed |
| CLI | Typer | Same Pydantic models, nice CLI |

---

## Structured Output Parsing

### The Problem
Network CLI output is unstructured text. Parsing with regex is tedious and error-prone.

### The Solution
Netmiko supports three structured output parsers:
- **TextFSM** - Template-based state machine (most mature)
- **TTP** - Template Text Parser (simpler syntax)
- **Genie** - Cisco pyATS (Cisco-focused)

**We'll use TextFSM with ntc-templates** - a community library with 500+ pre-built templates.

### Usage in Netmiko

```python
from netmiko import ConnectHandler

conn = ConnectHandler(device_type="aruba_os", ...)

# Without parsing - returns raw string
raw = conn.send_command("show vlan")
# "VLAN  Name      Status...\n1     default   Port-based..."

# With TextFSM - returns list of dicts!
parsed = conn.send_command("show vlan", use_textfsm=True)
# [{"vlan_id": "1", "name": "default", "status": "Port-based"}, ...]
```

### Available aruba_os Templates (ntc-templates)

| Command | Template | Returns |
|---------|----------|---------|
| `show version` | ✅ Built-in | hostname, version, uptime, model |
| `show vlan` | ✅ Built-in | vlan_id, name, status |
| `show arp` | ✅ Built-in | ip_address, mac_address, interface |
| `show ip interface brief` | ✅ Built-in | interface, ip_address, status |
| `show inventory` | ✅ Built-in | name, description, serial |
| `show hostname` | ✅ Built-in | hostname |

### Commands Needing Custom Templates

For S2500-specific commands without templates, we'll create custom TextFSM or TTP templates:

| Command | What We Need |
|---------|--------------|
| `show interface status` | port, status, vlan, speed, duplex |
| `show poe interface all` | port, poe_status, power_mw, priority |
| `show mac-address-table` | mac, vlan, port, type |
| `show interface <port>` | detailed port stats |

### Custom Template Location

```
switch-manager/
├── templates/
│   ├── textfsm/
│   │   ├── aruba_os_show_interface_status.textfsm
│   │   ├── aruba_os_show_poe_interface_all.textfsm
│   │   └── aruba_os_show_mac-address-table.textfsm
│   └── ttp/
│       └── aruba_os_show_interface_status.ttp
```

### Example: Custom TextFSM Template

**`aruba_os_show_interface_status.textfsm`**
```
Value PORT (\S+)
Value NAME (.*)
Value STATUS (up|down|disabled)
Value VLAN (\d+|trunk)
Value DUPLEX (full|half|auto)
Value SPEED (\d+|auto)
Value TYPE (\S+)

Start
  ^${PORT}\s+${NAME}\s+${STATUS}\s+${VLAN}\s+${DUPLEX}\s+${SPEED}\s+${TYPE} -> Record
```

### Example: TTP Template (Alternative)

TTP has a simpler, more readable syntax:

**`aruba_os_show_interface_status.ttp`**
```
<group name="ports">
{{ port }} {{ name | ORPHRASE }} {{ status }} {{ vlan }} {{ duplex }} {{ speed }} {{ type }}
</group>
```

### Driver Implementation

```python
class S2500Driver:
    def get_vlans(self) -> list[dict]:
        """Get VLANs with automatic parsing."""
        return self.connection.send_command(
            "show vlan", 
            use_textfsm=True
        )
    
    def get_port_status(self) -> list[dict]:
        """Get port status with custom template."""
        return self.connection.send_command(
            "show interface status",
            use_textfsm=True,
            textfsm_template="templates/textfsm/aruba_os_show_interface_status.textfsm"
        )
    
    def get_poe_status(self) -> list[dict]:
        """Get PoE status with TTP (alternative parser)."""
        raw = self.connection.send_command("show poe interface all")
        return self.connection.send_command(
            "show poe interface all",
            use_ttp=True,
            ttp_template="templates/ttp/aruba_os_show_poe.ttp"
        )
```

### Benefits for the UI

Structured data makes building the UI trivial:

```python
# API endpoint
@app.get("/api/ports")
async def get_ports():
    with S2500Driver(credentials) as driver:
        ports = driver.get_port_status()  # Already a list of dicts!
        return {"ports": ports}

# Jinja template
{% for port in ports %}
<div class="port {{ port.status }}">
    <span>{{ port.port }}</span>
    <span>{{ port.vlan }}</span>
</div>
{% endfor %}
```

### Fallback Strategy

```python
def get_port_status(self) -> list[dict]:
    """Try TextFSM first, fall back to regex."""
    try:
        return self.connection.send_command(
            "show interface status",
            use_textfsm=True
        )
    except Exception:
        # Fall back to manual parsing
        raw = self.connection.send_command("show interface status")
        return self._parse_interface_status_manual(raw)
```

---

## Key ArubaOS Commands Reference

```bash
# Status
show version
show interface status
show interface GE0/0/1
show vlan
show poe interface all
show mac-address-table
show running-config

# Configuration
configure terminal
vlan 10
  name "servers"
  exit
interface GE0/0/1
  description "Server port"
  switchport mode access
  switchport access vlan 10
  poe
  poe priority high
  no shutdown
  exit
write memory
```

---

## Phase 1 MVP

1. ✅ YAML config schema with Pydantic validation
2. ✅ Netmiko driver with basic commands
3. ✅ Diff engine (desired vs current)
4. ✅ Web UI: Dashboard + Port grid view
5. ✅ Web UI: View port details
6. ✅ CLI: `switchctl status`, `switchctl diff`

## Phase 2

1. Web UI: Edit port config (writes to YAML)
2. Web UI: Apply changes with confirmation
3. VLAN management UI
4. Config backup/restore

## Phase 3

1. Multi-switch support
2. Config templates/profiles
3. Scheduled config checks
4. Change history/audit log
5. Webhook notifications

---

## Questions to Resolve

1. **Port naming**: S2500 uses what format? `GE0/0/1`, `1/0/1`, or just `1`?
   - Need to test against real switch to confirm

2. **Authentication**: Store password in YAML (encrypted?) or prompt?
   - Suggest: Environment variable with `${VAR}` syntax

3. **Multi-switch**: Single YAML or directory of YAMLs?
   - Suggest: `config/switches/*.yaml` pattern

4. **Rollback**: Auto-generate rollback commands?
   - Nice to have for Phase 2

---

## Getting Started (for Claude Code)

```bash
# Create venv
python -m venv venv
source venv/bin/activate

# Install deps
pip install fastapi uvicorn netmiko pydantic pyyaml jinja2 typer

# Run in mock mode (no real switch)
MOCK_SWITCH=1 uvicorn app.web.main:app --reload

# Run CLI
python cli.py status --mock
python cli.py diff --mock
```
