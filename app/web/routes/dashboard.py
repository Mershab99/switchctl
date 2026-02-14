from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()

    ports_up = sum(1 for p in status.ports.values() if p.oper_status == "up")
    ports_down = sum(
        1 for p in status.ports.values()
        if p.oper_status == "down" and p.admin_status == "up"
    )
    ports_disabled = sum(1 for p in status.ports.values() if p.admin_status == "down")
    poe_active = sum(1 for p in status.ports.values() if p.poe_status == "delivering")
    total_poe_w = sum(p.poe_power_mw for p in status.ports.values()) / 1000

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "status": status,
        "config": config,
        "ports_up": ports_up,
        "ports_down": ports_down,
        "ports_disabled": ports_disabled,
        "poe_active": poe_active,
        "total_poe_w": round(total_poe_w, 1),
        "vlan_count": len(status.vlans),
    })
