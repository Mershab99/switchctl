# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**switchctl** is a Python web application for managing Aruba S2500 Mobility Access Switches using a declarative YAML configuration as the source of truth, with a web UI and CLI layered on top. Think Terraform-style diff/plan/apply, but for switch port and VLAN configuration.

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
# Web UI (mock mode, no real switch needed)
MOCK_SWITCH=1 uvicorn app.web.main:app --reload

# CLI
python cli.py status --mock
python cli.py diff --mock
```

## Testing

```bash
pytest
# For testing against a real switch, omit MOCK_SWITCH / --mock flags
```

## Architecture

Three-layer design: **Web UI / CLI** → **Core Engine** → **Switch Driver**

- **Config Loader** (`app/config_loader.py`): Loads YAML config, substitutes `${ENV_VAR}` patterns, expands port ranges (e.g. `"1-10"` → `["1"..."10"]`), merges `port_defaults` with per-port overrides, validates via Pydantic models.

- **Diff Engine** (`app/core/diff.py`): Compares desired state (from YAML) against current state (from switch). Produces `ConfigDiff` objects with resource type, action (create/update/delete), field-level changes, and the CLI commands needed.

- **Command Generator** (`app/core/commands.py`): Converts diffs into ordered ArubaOS CLI commands. VLANs must be created before ports reference them.

- **Switch Driver** (`app/drivers/aruba_os.py`): SSH via Netmiko with `device_type="aruba_os"` (not `aruba_osswitch`). Uses `use_textfsm=True` for structured output parsing. Custom TextFSM templates live in `templates/textfsm/` for commands not covered by ntc-templates (interface status, PoE, MAC table). A `MockS2500Driver` (`app/drivers/mock.py`) provides fake data for development.

- **Web UI** (`app/web/`): FastAPI + HTMX + Jinja2 + TailwindCSS (CDN). No JS build step. Key routes: `/` (dashboard), `/ports` (visual 48-port grid), `/vlans`, `/diff`, `POST /apply`.

- **CLI** (`cli.py`): Typer-based. Commands: `status`, `diff`, `apply [--save]`, `backup`.

## Key Design Decisions

- **Declarative config**: `switch.yaml` is the source of truth. The system reconciles desired vs actual state.
- **Port ranges**: YAML keys like `"1-10"` or `"1,3,5-8"` get expanded; `port_defaults` are merged under each port unless overridden.
- **Credentials**: Passwords use `${ENV_VAR}` syntax, resolved from environment at load time. Never hardcoded.
- **Netmiko + TextFSM**: Prefer `use_textfsm=True` for all read operations. Fall back to manual regex parsing only if TextFSM fails. For custom templates, pass `textfsm_template="templates/textfsm/..."`.
- **Port grid layout**: 48 copper ports displayed in two rows (odd top, even bottom) plus 4 SFP+ uplinks. Color-coded by status (green=up, gray=down, red=disabled, blue border=PoE active, orange=config drift).

## Pydantic Models (`app/models.py`)

Two model families:
- **Config models** (from YAML): `SwitchConfig`, `SwitchCredentials`, `VlanConfig`, `PortConfig`
- **Status models** (from switch): `SwitchStatus`, `PortStatus`, `ConfigDiff`

## Configuration File

See `switch.example.yaml` for the full schema. The config file path defaults to `config/switch.yaml`.
