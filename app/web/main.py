from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config_loader import load_config
from app.drivers import get_driver

from app.web.routes import dashboard, ports, vlans, api


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load config and connect driver on startup."""
    config_path = os.environ.get("SWITCH_CONFIG", "config/switch.yaml")
    try:
        app.state.config = load_config(config_path)
    except Exception as e:
        # Fall back to example config
        app.state.config = load_config("switch.example.yaml")

    app.state.driver = get_driver(app.state.config.credentials)
    app.state.driver.connect()
    yield
    app.state.driver.disconnect()


app = FastAPI(title="switchctl", lifespan=lifespan)

# Templates
template_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))

# Share templates with routes
app.state.templates = templates

# Include routers
app.include_router(dashboard.router)
app.include_router(ports.router)
app.include_router(vlans.router)
app.include_router(api.router)
